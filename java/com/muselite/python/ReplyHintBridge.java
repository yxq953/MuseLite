package com.muselite.python;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Toast;
import com.chaquo.python.Python;
import org.json.JSONObject;
import java.io.File;
import java.util.UUID;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/** Temporary accessibility overlay. No screenshot or model work runs on the UI thread. */
public final class ReplyHintBridge {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    // All state and clipboard commits are confined to the main thread.
    private static PhoneAccessibilityService service;
    private static LinearLayout panel;
    private static Button reply;
    private static WindowManager manager;
    private static WindowManager.LayoutParams layout;
    private static String session = "", token = "", request = "";
    private static boolean busy;

    private ReplyHintBridge() {}
    private interface UiTask { JSONObject run() throws Exception; }

    private static JSONObject ui(UiTask action) throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) return action.run();
        FutureTask<JSONObject> task = new FutureTask<>(() -> action.run());
        MAIN.post(task);
        try { return task.get(3, TimeUnit.SECONDS); }
        catch (Exception exc) { task.cancel(false); throw exc; }
    }

    private static int dp(int value) {
        return Math.round(value * service.getResources().getDisplayMetrics().density);
    }

    public static void close() {
        if (Looper.myLooper() == Looper.getMainLooper()) remove();
        else MAIN.post(ReplyHintBridge::remove);
    }

    private static void remove() {
        token = ""; session = ""; request = ""; busy = false;
        if (panel != null && manager != null) {
            try { manager.removeViewImmediate(panel); } catch (RuntimeException ignored) {}
        }
        panel = null; reply = null; service = null; manager = null; layout = null;
    }

    private static void guard(Activity activity) {
        if (!PhoneBridge.enabled(activity)) throw new IllegalStateException("请先在设置中启用手机控制");
        if (PhoneAccessibilityService.current() == null)
            throw new IllegalStateException("请先在系统无障碍设置中启用 MuseLite Python");
    }

    private static void validate(Activity activity, JSONObject args) throws Exception {
        guard(activity);
        if (panel == null || service != PhoneAccessibilityService.current() || token.isEmpty() ||
            !NativeUi.replyConversationIs(session) || activity.isFinishing() || activity.isDestroyed() ||
            !token.equals(args.getString("token")) || !session.equals(args.getString("session_id")) ||
            !busy || !request.equals(args.getString("request_id")))
            throw new IllegalStateException("当前聊天提示已关闭或请求已失效");
    }

    private static JSONObject show(Activity activity, JSONObject args) throws Exception {
        guard(activity);
        String sid = args.getString("session_id");
        if (sid.isEmpty()) throw new IllegalArgumentException("需要当前对话");
        if (!NativeUi.replyConversationIs(sid) || activity.isFinishing() || activity.isDestroyed())
            throw new IllegalStateException("当前对话已结束，无法开启聊天提示");
        remove();
        service = PhoneAccessibilityService.current();
        manager = (WindowManager) service.getSystemService(Context.WINDOW_SERVICE);
        session = sid; token = UUID.randomUUID().toString();
        panel = new LinearLayout(service);
        panel.setOrientation(LinearLayout.HORIZONTAL);
        panel.setPadding(dp(4), dp(4), dp(4), dp(4));
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(23, 101, 109)); background.setCornerRadius(dp(24));
        panel.setBackground(background); panel.setElevation(dp(8));
        reply = new Button(service);
        reply.setText("帮我回复"); reply.setTextSize(14); reply.setTextColor(Color.WHITE);
        reply.setBackgroundColor(Color.TRANSPARENT);
        panel.addView(reply, new LinearLayout.LayoutParams(dp(106), dp(44)));
        Button close = new Button(service);
        close.setText("×"); close.setTextSize(22); close.setTextColor(Color.WHITE);
        close.setContentDescription("关闭聊天提示"); close.setBackgroundColor(Color.TRANSPARENT);
        panel.addView(close, new LinearLayout.LayoutParams(dp(44), dp(44)));
        layout = new WindowManager.LayoutParams(-2, -2,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT);
        layout.gravity = Gravity.TOP | Gravity.LEFT;
        layout.x = Math.max(0, service.getResources().getDisplayMetrics().widthPixels - dp(170));
        layout.y = dp(180);
        try { manager.addView(panel, layout); }
        catch (RuntimeException exc) { remove(); throw exc; }
        // Drag the reply button to avoid covering chat text; a short tap still invokes it.
        reply.setOnTouchListener(new View.OnTouchListener() {
            float downX, downY; int startX, startY; boolean moved;
            @Override public boolean onTouch(View view, MotionEvent event) {
                if (panel == null) return false;
                if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    downX = event.getRawX(); downY = event.getRawY();
                    startX = layout.x; startY = layout.y; moved = false; return true;
                }
                if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
                    float dx = event.getRawX() - downX, dy = event.getRawY() - downY;
                    moved |= Math.abs(dx) + Math.abs(dy) > dp(8);
                    if (moved) {
                        android.util.DisplayMetrics metrics = service.getResources().getDisplayMetrics();
                        layout.x = Math.max(0, Math.min(metrics.widthPixels - panel.getWidth(), startX + (int) dx));
                        layout.y = Math.max(0, Math.min(metrics.heightPixels - panel.getHeight(), startY + (int) dy));
                        manager.updateViewLayout(panel, layout);
                    }
                    return true;
                }
                if (event.getActionMasked() == MotionEvent.ACTION_UP) {
                    if (!moved) view.performClick(); return true;
                }
                return event.getActionMasked() == MotionEvent.ACTION_CANCEL;
            }
        });
        reply.setOnClickListener(view -> {
            if (busy) return;
            busy = true; request = UUID.randomUUID().toString();
            reply.setText("截图中…");
            try {
                JSONObject data = new JSONObject().put("token", token).put("session_id", session)
                    .put("request_id", request);
                boolean accepted = Python.getInstance().getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", "chat_hint_reply", data.toString()).toBoolean();
                if (!accepted) throw new IllegalStateException("聊天提示尚未就绪，请重新开启");
            } catch (Exception exc) { failure(exc.getMessage()); }
        });
        close.setOnClickListener(view -> {
            String oldToken = token;
            remove(); // Invalidate before notifying Python, so an in-flight reply cannot copy.
            try {
                Python.getInstance().getModule("muselite_py.native_ui_callbacks")
                    .callAttr("on_action", "chat_hint_close", new JSONObject().put("token", oldToken).toString());
            } catch (Exception ignored) {}
        });
        return new JSONObject().put("enabled", true).put("token", token);
    }

    private static void restore() {
        if (panel != null) { panel.setVisibility(View.VISIBLE); reply.setText(busy ? "生成中…" : "帮我回复"); }
    }

    private static void failure(String message) {
        busy = false; request = ""; restore();
        if (service != null) Toast.makeText(service, message == null ? "回复生成失败" : message,
            Toast.LENGTH_LONG).show();
    }

    private static JSONObject capture(Activity activity, JSONObject args) throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper())
            throw new IllegalStateException("截图必须在后台线程执行");
        ui(() -> { validate(activity, args); panel.setVisibility(View.GONE); return new JSONObject(); });
        File file = null;
        try {
            Thread.sleep(250); // Allow the compositor to remove the overlay before capture.
            ui(() -> { validate(activity, args); return new JSONObject(); });
            PhoneAccessibilityService current = PhoneAccessibilityService.current();
            String app = current.chatPackage("");
            JSONObject image = current.screenshot(new File(activity.getCacheDir(), "phone-screenshots"));
            file = new File(image.getString("path"));
            if (!app.equals(current.chatPackage("")))
                throw new IllegalStateException("截图期间切换了应用，请重新点击");
            ui(() -> { validate(activity, args); restore(); return new JSONObject(); });
            image.put("package", app);
            return image;
        } catch (Exception exc) {
            if (file != null) file.delete();
            throw exc;
        }
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject input = new JSONObject(requestJson);
            String action = input.getString("action");
            JSONObject args = input.getJSONObject("params");
            JSONObject result;
            if (action.equals("capture")) result = capture(activity, args);
            else result = ui(() -> {
                switch (action) {
                    case "enable": return show(activity, args);
                    case "disable":
                        if (args.optString("token").isEmpty() || token.equals(args.optString("token"))) remove();
                        return new JSONObject().put("enabled", panel != null);
                    case "finish":
                        validate(activity, args);
                        String text = args.getString("text");
                        if (text.trim().isEmpty() || text.codePointCount(0, text.length()) > 10000)
                            throw new IllegalArgumentException("回复为空或过长");
                        ClipboardManager clipboard = (ClipboardManager) service.getSystemService(Context.CLIPBOARD_SERVICE);
                        if (clipboard == null) throw new IllegalStateException("系统剪贴板不可用");
                        clipboard.setPrimaryClip(ClipData.newPlainText("MuseLite 推荐回复", text));
                        busy = false; request = ""; restore();
                        Toast.makeText(service, "已复制，可粘贴后发送", Toast.LENGTH_SHORT).show();
                        return new JSONObject().put("written", true);
                    case "error":
                        if (token.equals(args.optString("token")) && request.equals(args.optString("request_id")))
                            failure(args.optString("message", "回复生成失败"));
                        return new JSONObject();
                    default: throw new IllegalArgumentException("未知聊天提示操作");
                }
            });
            return new JSONObject().put("result", result).toString();
        } catch (Exception exc) {
            Throwable cause = exc.getCause() == null ? exc : exc.getCause();
            try { return new JSONObject().put("error", cause.getMessage() == null ? cause.toString() : cause.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"聊天提示失败\"}"; }
        }
    }
}
