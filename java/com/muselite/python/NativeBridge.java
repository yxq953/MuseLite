package com.muselite.python;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.graphics.drawable.GradientDrawable;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Narrow Android API bridge. Python invokes call from a worker thread only. */
public final class NativeBridge {
    private static final ArrayList<WebView> tabs = new ArrayList<>();
    private static final Map<String, CompletableFuture<String>> pending = new HashMap<>();
    private static FrameLayout overlay;
    private static View dimLayer;
    private static LinearLayout browserPanel;
    private static LinearLayout browserToolbar;
    private static Button expandButton;
    private static FrameLayout browserContent;
    private static View previewTapTarget;
    private static boolean browserVisible;
    private static boolean browserExpanded;
    private static int selected = 0;
    private static File workspace;
    private static Activity owner;

    private NativeBridge() {}

    public static String nativeLibraryDir(Activity activity) {
        return activity.getApplicationInfo().nativeLibraryDir;
    }

    public static String filesDir(Activity activity) { return activity.getFilesDir().getAbsolutePath(); }

    public static String dnsConfig(Activity activity) {
        try {
            ConnectivityManager manager = (ConnectivityManager)
                activity.getSystemService(Context.CONNECTIVITY_SERVICE);
            Network network = manager == null ? null : manager.getActiveNetwork();
            LinkProperties properties = network == null ? null : manager.getLinkProperties(network);
            if (properties == null) return "";
            StringBuilder config = new StringBuilder();
            String domains = properties.getDomains();
            if (domains != null && !domains.isEmpty() && !domains.contains("\n"))
                config.append("search ").append(domains).append('\n');
            for (java.net.InetAddress server : properties.getDnsServers()) {
                String address = server.getHostAddress();
                if (address != null && !address.contains("\n"))
                    config.append("nameserver ").append(address).append('\n');
            }
            return config.toString();
        } catch (Exception ignored) {
            return "";
        }
    }

    public static void copyAsset(Activity activity, String name, String destination) throws Exception {
        File file = new File(destination);
        if (file.isFile() && file.length() > 0) return;
        File parent = file.getParentFile();
        if (parent == null || (!parent.isDirectory() && !parent.mkdirs()))
            throw new IllegalStateException("cannot create asset directory");
        File temporary = new File(destination + ".tmp");
        try (InputStream input = activity.getAssets().open(name);
             FileOutputStream output = new FileOutputStream(temporary)) {
            byte[] buffer = new byte[8192]; int size;
            while ((size = input.read(buffer)) >= 0) output.write(buffer, 0, size);
        }
        if (!temporary.renameTo(file)) throw new IllegalStateException("cannot stage Android asset");
    }

    private interface UiTask<T> { T run() throws Exception; }

    private static <T> T ui(Activity activity, UiTask<T> task) throws Exception {
        if (Thread.currentThread() == activity.getMainLooper().getThread())
            throw new IllegalStateException("NativeBridge.call must run off the Android UI thread");
        final Object[] result = new Object[1];
        final Exception[] error = new Exception[1];
        CountDownLatch latch = new CountDownLatch(1);
        activity.runOnUiThread(() -> {
            try { result[0] = task.run(); }
            catch (Exception exc) { error[0] = exc; }
            finally { latch.countDown(); }
        });
        if (!latch.await(15, TimeUnit.SECONDS)) throw new RuntimeException("Android UI timeout");
        if (error[0] != null) throw error[0];
        @SuppressWarnings("unchecked") T value = (T) result[0];
        return value;
    }

    private static JSONObject ok(Object value) throws Exception {
        JSONObject result = new JSONObject();
        result.put("result", value);
        return result;
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject request = new JSONObject(requestJson);
            String action = request.getString("action");
            JSONObject params = request.optJSONObject("params");
            if (params == null) params = new JSONObject();
            final JSONObject input = params;
            if (action.equals("configure")) {
                String path = params.getString("workspace");
                workspace = new File(path).getCanonicalFile();
                return ok(true).toString();
            }
            ensure(activity);
            if (action.equals("show_browser")) {
                boolean visible = params.optBoolean("visible", true);
                ui(activity, () -> { show(visible); return null; });
                return ok(visible).toString();
            }
            if (action.equals("set_browser_preview")) {
                String title = params.optString("title", "网页结果");
                String url = params.optString("url", "");
                String text = params.optString("text", "");
                ui(activity, () -> { updateBrowserPreview(title, url, text); return null; });
                return ok(true).toString();
            }
            if (action.equals("new_tab")) {
                int id = ui(activity, () -> {
                    if (tabs.size() >= 3) throw new IllegalStateException("最多 3 个标签页");
                    tabs.add(createTab(activity)); selected = tabs.size() - 1;
                    attachSelected(); return selected;
                });
                return ok(id).toString();
            }
            if (action.equals("close_tab")) {
                int id = params.optInt("tab_id", selected);
                ui(activity, () -> {
                    if (id < 0 || id >= tabs.size()) throw new IllegalArgumentException("标签页不存在");
                    WebView removed = tabs.remove(id); overlay.removeView(removed); removed.destroy();
                    if (tabs.isEmpty()) tabs.add(createTab(activity));
                    if (id < selected) selected--;
                    selected = Math.min(selected, tabs.size() - 1); attachSelected(); return null;
                });
                return ok(true).toString();
            }
            if (action.equals("list_tabs")) {
                return ui(activity, () -> {
                    JSONArray list = new JSONArray();
                    for (int i = 0; i < tabs.size(); i++) {
                        WebView web = tabs.get(i);
                        JSONObject item = new JSONObject(); item.put("tab_id", i);
                        item.put("url", web.getUrl()); item.put("title", web.getTitle());
                        item.put("selected", i == selected); list.put(item);
                    }
                    return ok(list).toString();
                });
            }
            int id = params.optInt("tab_id", -1);
            WebView web = ui(activity, () -> {
                if (id >= 0) {
                    if (id >= tabs.size()) throw new IllegalArgumentException("标签页不存在");
                    selected = id; attachSelected();
                }
                return tabs.get(selected);
            });
            switch (action) {
                case "navigate": return navigate(activity, web, params.getString("url")).toString();
                case "screenshot": return screenshot(activity, web, params).toString();
                case "get_cookies": return getCookies(activity, web, params).toString();
                case "set_cookies": return setCookies(activity, web, params).toString();
                case "fetch": return fetch(activity, web, params).toString();
                case "set_user_agent": return ui(activity, () -> {
                    String profile = input.optString("user_agent", "mobile_chrome");
                    String ua = profile.equals("desktop_chrome")
                        ? "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/134 Safari/537.36"
                        : android.webkit.WebSettings.getDefaultUserAgent(activity);
                    web.getSettings().setUserAgentString(ua); web.reload(); return ok(profile).toString();
                });
                case "set_viewport": return ui(activity, () -> {
                    if (input.optBoolean("reset", false)) {
                        web.getLayoutParams().width = ViewGroup.LayoutParams.MATCH_PARENT;
                        web.getLayoutParams().height = ViewGroup.LayoutParams.MATCH_PARENT;
                    } else {
                        int w = input.getInt("viewport_width"), h = input.getInt("viewport_height");
                        if (w < 200 || h < 200 || w > 4096 || h > 4096)
                            throw new IllegalArgumentException("无效视口尺寸");
                        web.getLayoutParams().width = w; web.getLayoutParams().height = h;
                    }
                    web.requestLayout(); return ok(true).toString();
                });
                default: return evaluate(activity, web, action, params).toString();
            }
        } catch (Exception exc) {
            try { return new JSONObject().put("error", exc.getMessage() == null ? exc.toString() : exc.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"bridge failure\"}"; }
        }
    }

    private static void ensure(Activity activity) throws Exception {
        ui(activity, () -> {
            if (owner != activity || overlay == null) {
                for (WebView tab : tabs) tab.destroy();
                tabs.clear(); owner = activity; selected = 0;
                dimLayer = new View(activity);
                dimLayer.setBackgroundColor(Color.argb(105, 0, 0, 0));
                dimLayer.setVisibility(View.GONE);
                dimLayer.setClickable(true);
                activity.addContentView(dimLayer, new ViewGroup.LayoutParams(-1, -1));
                overlay = new FrameLayout(activity);
                FrameLayout.LayoutParams params = miniParams(activity);
                activity.addContentView(overlay, params);
                overlay.setElevation(24f);
                tabs.add(createTab(activity)); attachSelected(); show(false);
            }
            return null;
        });
    }

    private static void show(boolean visible) {
        if (visible && !NativeUi.isChatScreen(owner)) visible = false;
        browserVisible = visible;
        if (visible) {
            setBrowserLayout(owner, browserExpanded);
        } else {
            browserExpanded = false;
            if (dimLayer != null) dimLayer.setVisibility(View.GONE);
            if (browserPanel != null) setBrowserLayout(owner, false);
        }
        overlay.setTranslationX(visible ? 0 : overlay.getResources().getDisplayMetrics().widthPixels + 50);
    }

    static void onScreenChanged(boolean chat) {
        if (chat || overlay == null) return;
        show(false);
        browserExpanded = false;
        setBrowserLayout(owner, false);
    }

    static void positionPreview(Activity activity) {
        if (!browserVisible || browserExpanded || owner != activity || overlay == null) return;
        int bottomMargin = previewBottomMargin(activity);
        FrameLayout.LayoutParams params = (FrameLayout.LayoutParams) overlay.getLayoutParams();
        if (params.bottomMargin != bottomMargin) {
            params.bottomMargin = bottomMargin;
            overlay.setLayoutParams(params);
        }
    }

    private static int dp(Activity activity, int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    private static FrameLayout.LayoutParams miniParams(Activity activity) {
        int width = Math.round(activity.getResources().getDisplayMetrics().widthPixels * 0.28f);
        FrameLayout.LayoutParams result = new FrameLayout.LayoutParams(width, dp(activity, 78));
        result.gravity = android.view.Gravity.BOTTOM | android.view.Gravity.LEFT;
        result.leftMargin = dp(activity, 12);
        result.bottomMargin = previewBottomMargin(activity);
        return result;
    }

    private static int previewBottomMargin(Activity activity) {
        int anchorTop = NativeUi.previewAnchorTopOnScreen(activity);
        if (anchorTop < 0 || overlay == null || overlay.getParent() == null) return dp(activity, 160);
        View parent = (View) overlay.getParent();
        int[] location = new int[2];
        parent.getLocationOnScreen(location);
        // Account for the panel's 4dp shadow inset to leave a visible 12dp gap.
        return Math.max(0, location[1] + parent.getHeight() - anchorTop + dp(activity, 8));
    }

    private static FrameLayout.LayoutParams expandedParams(Activity activity) {
        View parent = overlay == null ? null : (View) overlay.getParent();
        int availableHeight = parent == null ? activity.getResources().getDisplayMetrics().heightPixels
                                             : parent.getHeight();
        int height = Math.round(availableHeight * 0.85f);
        FrameLayout.LayoutParams result = new FrameLayout.LayoutParams(-1, height);
        result.gravity = android.view.Gravity.BOTTOM;
        return result;
    }

    private static void setBrowserLayout(Activity activity, boolean expanded) {
        if (activity == null || overlay == null || browserPanel == null) return;
        boolean opening = expanded && !browserExpanded;
        browserExpanded = expanded;
        if (dimLayer != null) {
            dimLayer.animate().cancel();
            dimLayer.setVisibility(expanded ? View.VISIBLE : View.GONE);
            if (opening) {
                dimLayer.setAlpha(0f);
                dimLayer.animate().alpha(1f).setDuration(220).start();
            } else if (expanded) {
                dimLayer.setAlpha(1f);
            }
        }
        ViewGroup.LayoutParams current = overlay.getLayoutParams();
        ViewGroup.LayoutParams next = expanded ? expandedParams(activity) : miniParams(activity);
        current.width = next.width;
        current.height = next.height;
        if (current instanceof FrameLayout.LayoutParams && next instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams from = (FrameLayout.LayoutParams) current;
            FrameLayout.LayoutParams to = (FrameLayout.LayoutParams) next;
            from.gravity = to.gravity;
            from.leftMargin = to.leftMargin;
            from.topMargin = to.topMargin;
            from.rightMargin = to.rightMargin;
            from.bottomMargin = to.bottomMargin;
        }
        overlay.setLayoutParams(current);
        overlay.animate().cancel();
        if (opening) {
            overlay.setTranslationY(next.height);
            overlay.animate().translationY(0f).setDuration(260).start();
        } else {
            overlay.setTranslationY(0f);
        }
        FrameLayout.LayoutParams panelParams = (FrameLayout.LayoutParams) browserPanel.getLayoutParams();
        int inset = expanded ? 0 : dp(activity, 4);
        panelParams.setMargins(inset, inset, inset, inset);
        browserPanel.setLayoutParams(panelParams);
        browserPanel.setElevation(dp(activity, expanded ? 3 : 9));
        GradientDrawable outline = new GradientDrawable();
        outline.setColor(Color.TRANSPARENT);
        outline.setStroke(dp(activity, expanded ? 1 : 2),
            expanded ? Color.rgb(205, 219, 240) : Color.rgb(158, 172, 224));
        outline.setCornerRadius(dp(activity, 6));
        browserPanel.setForeground(outline);
        int toolbarHeight = dp(activity, expanded ? 56 : 0);
        if (browserToolbar != null) {
            browserToolbar.setVisibility(expanded ? View.VISIBLE : View.GONE);
            ViewGroup.LayoutParams toolbarParams = browserToolbar.getLayoutParams();
            toolbarParams.height = toolbarHeight;
            browserToolbar.setLayoutParams(toolbarParams);
        }
        if (expandButton != null) expandButton.setText(expanded ? "收回" : "放大");
        if (browserContent != null && browserContent.getChildCount() > 0) {
            WebView web = (WebView) browserContent.getChildAt(0);
            FrameLayout.LayoutParams webParams = (FrameLayout.LayoutParams) web.getLayoutParams();
            if (expanded) {
                web.setScaleX(1f);
                web.setScaleY(1f);
                webParams.width = -1;
                webParams.height = -1;
            } else {
                int miniWidth = miniParams(activity).width;
                int pageWidth = activity.getResources().getDisplayMetrics().widthPixels;
                float scale = (float) miniWidth / pageWidth;
                webParams.width = pageWidth;
                webParams.height = Math.round(dp(activity, 78) / scale);
                web.setPivotX(0f);
                web.setPivotY(0f);
                web.setScaleX(scale);
                web.setScaleY(scale);
            }
            web.setLayoutParams(webParams);
            if (previewTapTarget != null)
                previewTapTarget.setVisibility(expanded ? View.GONE : View.VISIBLE);
        }
    }

    private static void updateBrowserPreview(String title, String url, String text) {
        if (!tabs.isEmpty()) tabs.get(selected).invalidate();
    }

    private static void attachSelected() {
        overlay.removeAllViews();
        if (browserPanel != null && browserPanel.getParent() instanceof ViewGroup)
            ((ViewGroup) browserPanel.getParent()).removeView(browserPanel);
        WebView web = tabs.get(selected);
        ViewGroup.LayoutParams previous = web.getLayoutParams();
        int width = previous == null ? -1 : previous.width;
        int height = previous == null ? -1 : previous.height;
        if (web.getParent() instanceof ViewGroup) ((ViewGroup) web.getParent()).removeView(web);
        browserPanel = new LinearLayout(owner);
        browserPanel.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable panelBackground = new GradientDrawable();
        panelBackground.setColor(Color.WHITE);
        panelBackground.setStroke(dp(owner, 1), Color.rgb(205, 219, 240));
        panelBackground.setCornerRadius(dp(owner, 6));
        browserPanel.setBackground(panelBackground);
        browserPanel.setClipToOutline(true);
        browserPanel.setElevation(dp(owner, 3));
        overlay.addView(browserPanel, new FrameLayout.LayoutParams(-1, -1));

        browserToolbar = new LinearLayout(owner);
        browserToolbar.setGravity(android.view.Gravity.CENTER_VERTICAL);
        int density = Math.round(owner.getResources().getDisplayMetrics().density);
        int barHeight = 56 * density;
        browserToolbar.setPadding(8 * density, 0, 8 * density, 0);
        browserToolbar.setBackgroundColor(Color.WHITE);
        browserToolbar.addView(new View(owner), new LinearLayout.LayoutParams(0, 1, 1f));
        Button back = browserButton(owner, "‹", "后退", 18);
        back.setOnClickListener(view -> { if (web.canGoBack()) web.goBack(); });
        browserToolbar.addView(back, browserButtonParams(owner, 42));
        Button forward = browserButton(owner, "›", "前进", 18);
        forward.setOnClickListener(view -> { if (web.canGoForward()) web.goForward(); });
        browserToolbar.addView(forward, browserButtonParams(owner, 42));
        expandButton = browserButton(owner, "收回", "收回网页卡片", 12);
        expandButton.setOnClickListener(view -> setBrowserLayout(owner, browserExpanded ? false : true));
        browserToolbar.addView(expandButton, browserButtonParams(owner, 58));
        Button close = browserButton(owner, "×", "关闭网页卡片", 18);
        close.setOnClickListener(view -> show(false));
        browserToolbar.addView(close, browserButtonParams(owner, 42));
        browserPanel.addView(browserToolbar, new LinearLayout.LayoutParams(-1, barHeight));

        browserContent = new FrameLayout(owner);
        browserContent.setBackgroundColor(Color.WHITE);
        browserContent.setClipChildren(true);
        browserPanel.addView(browserContent, new LinearLayout.LayoutParams(-1, 0, 1f));
        browserContent.addView(web, new FrameLayout.LayoutParams(-1, -1));
        previewTapTarget = new View(owner);
        previewTapTarget.setContentDescription("放大网页预览");
        previewTapTarget.setOnClickListener(view -> setBrowserLayout(owner, true));
        browserContent.addView(previewTapTarget, new FrameLayout.LayoutParams(-1, -1));
        setBrowserLayout(owner, browserExpanded);
    }

    private static Button browserButton(Activity activity, String label,
                                        String description, int textSize) {
        Button result = new Button(activity);
        result.setText(label);
        result.setTextSize(textSize);
        result.setAllCaps(false);
        result.setTextColor(Color.WHITE);
        result.setContentDescription(description);
        result.setPadding(0, 0, 0, 0);
        result.setBackground(NativeUi.filledButtonBackground(activity));
        return result;
    }

    private static LinearLayout.LayoutParams browserButtonParams(Activity activity, int widthDp) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            dp(activity, widthDp), dp(activity, 40));
        params.leftMargin = dp(activity, 5);
        return params;
    }

    private static WebView createTab(Activity activity) {
        WebView web = new WebView(activity);
        web.setBackgroundColor(Color.WHITE);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setSupportMultipleWindows(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        web.addJavascriptInterface(new Callback(), "MuseLiteBridge");
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (!url.startsWith("https://muselite.local/")) return null;
                try {
                    File file = workspaceFile(url.substring("https://muselite.local/".length()));
                    String mime = java.net.URLConnection.guessContentTypeFromName(file.getName());
                    return new WebResourceResponse(mime == null ? "application/octet-stream" : mime,
                        "UTF-8", new java.io.FileInputStream(file));
                } catch (Exception exc) {
                    return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found",
                        new HashMap<>(), new java.io.ByteArrayInputStream(new byte[0]));
                }
            }
        });
        return web;
    }

    private static File workspaceFile(String relative) throws Exception {
        if (workspace == null) throw new IllegalStateException("workspace not configured");
        File file = new File(workspace, java.net.URLDecoder.decode(relative, "UTF-8")).getCanonicalFile();
        if (!file.toPath().startsWith(workspace.toPath())) throw new SecurityException("path outside workspace");
        return file;
    }

    private static JSONObject navigate(Activity activity, WebView web, String url) throws Exception {
        if (url.startsWith("muselite://workspace/"))
            url = "https://muselite.local/" + url.substring("muselite://workspace/".length());
        if (!url.startsWith("https://") && !url.startsWith("http://"))
            throw new IllegalArgumentException("仅支持 HTTP(S) 与 muselite://workspace/ URL");
        String target = url;
        CountDownLatch latch = new CountDownLatch(1);
        final String[] error = new String[1];
        ui(activity, () -> {
            web.setWebViewClient(new WebViewClient() {
                @Override public void onPageFinished(WebView view, String page) { latch.countDown(); }
                @Override public void onReceivedError(WebView view, WebResourceRequest req,
                        android.webkit.WebResourceError err) {
                    if (req.isForMainFrame()) { error[0] = err.getDescription().toString(); latch.countDown(); }
                }
                @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                    String requested = req.getUrl().toString();
                    if (!requested.startsWith("https://muselite.local/")) return null;
                    try {
                        File file = workspaceFile(requested.substring("https://muselite.local/".length()));
                        String mime = java.net.URLConnection.guessContentTypeFromName(file.getName());
                        return new WebResourceResponse(mime == null ? "application/octet-stream" : mime,
                            "UTF-8", new java.io.FileInputStream(file));
                    } catch (Exception exc) { return null; }
                }
            });
            web.loadUrl(target); return null;
        });
        if (!latch.await(30, TimeUnit.SECONDS)) throw new RuntimeException("网页加载超时");
        if (error[0] != null) throw new RuntimeException(error[0]);
        return ui(activity, () -> new JSONObject().put("url", web.getUrl()).put("title", web.getTitle()));
    }

    private static final class Callback {
        @JavascriptInterface public void complete(String id, String data) {
            synchronized (pending) {
                CompletableFuture<String> future = pending.remove(id);
                if (future != null) future.complete(data);
            }
        }
    }

    private static JSONObject javascript(Activity activity, WebView web, String script) throws Exception {
        String id = UUID.randomUUID().toString();
        CompletableFuture<String> future = new CompletableFuture<>();
        synchronized (pending) { pending.put(id, future); }
        String wrapper = "(async()=>{try{const value=await(async()=>{" + script +
            "})();MuseLiteBridge.complete(" + JSONObject.quote(id) +
            ",JSON.stringify({result:value===undefined?null:value}));}catch(e){MuseLiteBridge.complete(" +
            JSONObject.quote(id) + ",JSON.stringify({error:String(e)}));}})()";
        ui(activity, () -> { web.evaluateJavascript(wrapper, null); return null; });
        try { return new JSONObject(future.get(20, TimeUnit.SECONDS)); }
        finally { synchronized (pending) { pending.remove(id); } }
    }

    private static JSONObject evaluate(Activity activity, WebView web, String action, JSONObject p) throws Exception {
        String script;
        String selector = JSONObject.quote(p.optString("selector", ""));
        switch (action) {
            case "execute_js": script = p.getString("script"); break;
            case "get_text": script = "return " + (p.has("selector")
                ? "document.querySelector(" + selector + ")?.innerText || ''"
                : "document.body?.innerText || ''"); break;
            case "get_readable": script =
                "let selectors=['article','[role=main]','main','.post-content','.article-body','.entry-content','#content','.content'];" +
                "let found=selectors.map(s=>[s,document.querySelector(s)]).find(x=>x[1]&&(x[1].innerText||'').trim());" +
                "let e=found?found[1]:document.body;let text=(e?.innerText||'').replace(/\\s+/g,' ').trim().slice(0,15000);" +
                "return {title:document.title,url:location.href,text:text,length:text.length,source:found?found[0]:'document.body'}";
                break;
            case "get_page_info": script = "return {title:document.title,url:location.href," +
                "description:document.querySelector('meta[name=description]')?.content||''," +
                "scrollY:scrollY,scrollHeight:document.body?.scrollHeight||0," +
                "viewportWidth:innerWidth,viewportHeight:innerHeight,readyState:document.readyState," +
                "forms:document.forms.length,links:document.links.length,images:document.images.length}"; break;
            case "get_backbone": script = "let max=" + Math.min(10, Math.max(1, p.optInt("max_depth", 5))) +
                ";function walk(e,d){if(d>max)return null;return {tag:e.tagName,id:e.id,role:e.getAttribute('role'),text:(e.innerText||'').slice(0,120),children:Array.from(e.children).slice(0,30).map(c=>walk(c,d+1))}}return walk(document.body,0)"; break;
            case "find_elements": script = "let es=document.querySelectorAll(" +
                (p.has("selector") ? selector : "'a,button,input,textarea,select'") +
                ");return {count:es.length,shown:Math.min(es.length,20),elements:Array.from(es).slice(0,20).map((e,i)=>{" +
                "let r=e.getBoundingClientRect();return {index:i,tag:e.tagName,id:e.id||null," +
                "className:e.className||null,text:(e.innerText||e.value||'').slice(0,80),href:e.href||null," +
                "rect:{x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)," +
                "pageX:Math.round(r.x+scrollX),pageY:Math.round(r.y+scrollY)," +
                "visible:r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0}}})}"; break;
            case "click": {
                String target = p.has("selector") ? "document.querySelector(" + selector + ")" :
                    "document.elementFromPoint(" + p.optInt("coordinate_x") + "," + p.optInt("coordinate_y") + ")";
                script = "let e=" + target + ";if(!e)throw Error('element not found');e.click();return true"; break;
            }
            case "type": script = "let e=document.querySelector(" + selector +
                ");if(!e)throw Error('element not found');e.focus();e.value=" + JSONObject.quote(p.getString("text")) +
                ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true"; break;
            case "hover": script = "let e=document.querySelector(" + selector +
                ");if(!e)throw Error('element not found');e.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));return true"; break;
            case "scroll": script = "let e=" + (p.has("selector") ? "document.querySelector(" + selector + ")" : "window") +
                ";if(!e)throw Error('scroll target not found');e.scrollBy(0," +
                (p.optString("direction", "down").equals("up") ? "-" : "") +
                Math.min(10000, Math.abs(p.optInt("amount", 500))) + ");return true"; break;
            default: throw new IllegalArgumentException("未知浏览器操作：" + action);
        }
        return javascript(activity, web, script);
    }

    private static JSONObject screenshot(Activity activity, WebView web, JSONObject p) throws Exception {
        int pageHeight = 0;
        if (p.optBoolean("full_page", false)) {
            JSONObject size = javascript(activity, web,
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)");
            pageHeight = Math.min(32768, Math.max(1, size.optInt("result", 1)));
        }
        final int targetHeight = pageHeight;
        return ui(activity, () -> {
            int width = Math.min(4096, Math.max(1, web.getWidth()));
            int height = targetHeight == 0 ? Math.min(32768, Math.max(1, web.getHeight())) : targetHeight;
            if ((long) width * height > 12_000_000L)
                throw new IllegalArgumentException("截图尺寸过大，请缩小视口或关闭 full_page");
            int oldWidth = web.getWidth(), oldHeight = web.getHeight();
            if (targetHeight > oldHeight) {
                web.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
                web.layout(0, 0, width, height);
            }
            Bitmap image = Bitmap.createBitmap(width, height, Bitmap.Config.RGB_565);
            Canvas canvas = new Canvas(image); web.draw(canvas);
            if (targetHeight > oldHeight) web.layout(0, 0, oldWidth, oldHeight);
            File folder = new File(workspace, "browser");
            if (!folder.isDirectory() && !folder.mkdirs()) throw new RuntimeException("cannot create browser folder");
            String name = "screenshot-" + UUID.randomUUID() + ".jpg";
            File output = new File(folder, name);
            try (FileOutputStream stream = new FileOutputStream(output)) {
                image.compress(Bitmap.CompressFormat.JPEG, 75, stream);
            }
            image.recycle();
            return new JSONObject().put("path", output.getAbsolutePath())
                .put("workspace_path", "/var/muselite/workspace/browser/" + name)
                .put("width", width).put("height", height);
        });
    }

    private static JSONObject getCookies(Activity activity, WebView web, JSONObject p) throws Exception {
        String url = ui(activity, () -> web.getUrl());
        if (url == null || !url.startsWith("http")) throw new IllegalStateException("先打开网页");
        String raw = ui(activity, () -> CookieManager.getInstance().getCookie(url));
        JSONArray names = new JSONArray();
        JSONArray keywords = p.optJSONArray("keywords");
        String singleKeyword = keywords == null ? p.optString("keywords", "").toLowerCase() : "";
        boolean fuzzy = p.optBoolean("fuzzy", false);
        StringBuilder exports = new StringBuilder();
        if (raw != null) for (String entry : raw.split(";")) {
            String[] pair = entry.trim().split("=", 2);
            if (pair.length != 2) continue;
            String name = pair[0];
            boolean matched = keywords == null || keywords.length() == 0;
            if (keywords != null) for (int i = 0; i < keywords.length(); i++) {
                String word = keywords.optString(i, "").toLowerCase();
                if (!word.isEmpty() && (fuzzy ? name.toLowerCase().contains(word) : name.equalsIgnoreCase(word)))
                    matched = true;
            }
            if (!singleKeyword.isEmpty() && !(fuzzy ? name.toLowerCase().contains(singleKeyword)
                    : name.equalsIgnoreCase(singleKeyword))) matched = false;
            if (!matched) continue;
            names.put(name);
            String variable = "COOKIE_" + name.replaceAll("[^A-Za-z0-9_]", "_");
            String escaped = pair[1].replace("'", "'\\''");
            exports.append("export ").append(variable).append("='").append(escaped).append("'\n");
        }
        File folder = new File(workspace, "browser");
        if (!folder.isDirectory() && !folder.mkdirs()) throw new RuntimeException("cannot create browser folder");
        String filename = "cookies-" + UUID.randomUUID() + ".sh";
        File env = new File(folder, filename);
        try (FileOutputStream output = new FileOutputStream(env)) {
            output.write(exports.toString().getBytes(StandardCharsets.UTF_8));
        }
        return new JSONObject().put("names", names).put("count", names.length())
            .put("env_path", "/var/muselite/workspace/browser/" + filename);
    }

    private static JSONObject setCookies(Activity activity, WebView web, JSONObject p) throws Exception {
        String url = ui(activity, () -> web.getUrl());
        if (url == null || !url.startsWith("http")) throw new IllegalStateException("先打开网页");
        JSONArray input = p.getJSONArray("cookies");
        URL current = new URL(url);
        for (int i = 0; i < input.length(); i++) {
            JSONObject cookie = input.getJSONObject(i);
            String domain = cookie.optString("domain", current.getHost());
            if (domain.startsWith(".")) domain = domain.substring(1);
            if (!current.getHost().equals(domain) && !current.getHost().endsWith("." + domain))
                throw new SecurityException("Cookie 域名不属于当前网站");
            String name = cookie.getString("name"), content = cookie.getString("value");
            if (name.matches(".*[;=\\r\\n].*") || content.matches(".*[;\\r\\n].*"))
                throw new IllegalArgumentException("无效 Cookie 内容");
            String value = name + "=" + content +
                "; Path=" + cookie.optString("path", "/") + "; Domain=" + domain +
                (cookie.optBoolean("secure", true) ? "; Secure" : "") +
                (cookie.optBoolean("http_only", false) ? "; HttpOnly" : "") +
                (cookie.has("expires") ? "; Expires=" +
                    new java.text.SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss 'GMT'", java.util.Locale.US)
                        {{ setTimeZone(java.util.TimeZone.getTimeZone("GMT")); }}
                        .format(new java.util.Date(cookie.getLong("expires") * 1000L)) : "");
            ui(activity, () -> { CookieManager.getInstance().setCookie(url, value); return null; });
        }
        ui(activity, () -> { CookieManager.getInstance().flush(); return null; });
        return new JSONObject().put("written", input.length());
    }

    private static JSONObject fetch(Activity activity, WebView web, JSONObject p) throws Exception {
        String current = ui(activity, () -> web.getUrl());
        if (current == null) throw new IllegalStateException("先打开网页");
        String requested = p.getString("url");
        if (requested.startsWith("blob:") || requested.startsWith("data:")) {
            JSONObject response = javascript(activity, web,
                "const r=await fetch(" + JSONObject.quote(requested) + ");" +
                "if(!r.ok)throw Error('HTTP '+r.status);" +
                "const b=await r.blob();if(b.size>8000000)throw Error('下载超过 8 MB');" +
                "const data=await new Promise((resolve,reject)=>{const f=new FileReader();" +
                "f.onload=()=>resolve(f.result);f.onerror=()=>reject(f.error);f.readAsDataURL(b)});" +
                "return {data:data,mime:b.type}");
            JSONObject payload = response.getJSONObject("result");
            String data = payload.getString("data");
            byte[] bytes = Base64.decode(data.substring(data.indexOf(',') + 1), Base64.DEFAULT);
            File folder = browserFolder();
            String name = "download-" + UUID.randomUUID();
            File file = new File(folder, name);
            try (FileOutputStream output = new FileOutputStream(file)) { output.write(bytes); }
            return new JSONObject().put("path", file.getAbsolutePath())
                .put("workspace_path", "/var/muselite/workspace/browser/" + name)
                .put("bytes", bytes.length).put("mime", payload.optString("mime"));
        }
        if (requested.startsWith("muselite://workspace/"))
            requested = "https://muselite.local/" + requested.substring("muselite://workspace/".length());
        URL url = new URL(new URL(current), requested);
        if (!url.getProtocol().equals("https") && !url.getProtocol().equals("http"))
            throw new IllegalArgumentException("仅支持 HTTP(S) 下载");
        if (url.getHost().equals("muselite.local")) {
            File file = workspaceFile(url.getPath().substring(1));
            return new JSONObject().put("path", file.getAbsolutePath())
                .put("workspace_path", "/var/muselite/workspace/" + url.getPath().substring(1))
                .put("bytes", file.length());
        }
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(10000); connection.setReadTimeout(20000);
        String cookies = ui(activity, () -> CookieManager.getInstance().getCookie(url.toString()));
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);
        try {
            int code = connection.getResponseCode();
            if (code < 200 || code >= 300) throw new RuntimeException("HTTP " + code);
            File folder = browserFolder();
            String name = "download-" + UUID.randomUUID();
            File file = new File(folder, name);
            long count = 0;
            try (InputStream input = connection.getInputStream(); FileOutputStream output = new FileOutputStream(file)) {
                byte[] buf = new byte[8192]; int n;
                while ((n = input.read(buf)) >= 0) {
                    count += n; if (count > 50_000_000) throw new RuntimeException("下载超过 50 MB");
                    output.write(buf, 0, n);
                }
            } catch (Exception exc) {
                file.delete();
                throw exc;
            }
            return new JSONObject().put("path", file.getAbsolutePath())
                .put("workspace_path", "/var/muselite/workspace/browser/" + name)
                .put("bytes", count).put("mime", connection.getContentType());
        } finally { connection.disconnect(); }
    }

    private static File browserFolder() {
        if (workspace == null) throw new IllegalStateException("workspace not configured");
        File folder = new File(workspace, "browser");
        if (!folder.isDirectory() && !folder.mkdirs())
            throw new RuntimeException("cannot create browser folder");
        return folder;
    }
}
