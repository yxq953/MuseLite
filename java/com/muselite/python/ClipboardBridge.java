package com.muselite.python;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Looper;
import org.json.JSONObject;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/** Explicit text-only clipboard access. No listeners or background polling. */
public final class ClipboardBridge {
    private static final int MAX_CHARS = 50000;
    private ClipboardBridge() {}

    private static JSONObject perform(Activity activity, String action, JSONObject args) throws Exception {
        ClipboardManager clipboard = (ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard == null) throw new IllegalStateException("系统剪贴板不可用");
        if (action.equals("read")) {
            // Android 10+ silently denies background clipboard reads. Check before querying.
            if (!activity.hasWindowFocus())
                throw new IllegalStateException("Android 限制后台读取剪贴板，请回到 MuseLite 前台后重试");
            int maxChars = args.optInt("max_chars", 12000);
            if (maxChars < 1 || maxChars > MAX_CHARS)
                throw new IllegalArgumentException("max_chars 必须在 1 到 50000 之间");
            ClipData clip = clipboard.getPrimaryClip();
            if (clip == null || clip.getItemCount() == 0)
                return new JSONObject().put("empty", true).put("content", "").put("truncated", false);
            CharSequence value = clip.getItemAt(0).getText();
            if (value == null)
                throw new IllegalArgumentException("剪贴板内容不是文本，暂不支持读取图片、文件或 URI");
            // Avoid allocating or coercing arbitrary URI/Intent clipboard payloads.
            int end = 0, count = 0;
            while (end < value.length() && count < maxChars) {
                char ch = value.charAt(end++);
                if (Character.isHighSurrogate(ch) && end < value.length() && Character.isLowSurrogate(value.charAt(end))) end++;
                count++;
            }
            return new JSONObject().put("empty", value.length() == 0)
                .put("content", value.subSequence(0, end).toString())
                .put("chars", count).put("truncated", end < value.length())
                .put("items", clip.getItemCount());
        }
        if (action.equals("write")) {
            Object raw = args.get("text");
            if (!(raw instanceof String)) throw new IllegalArgumentException("text 必须是文本");
            String text = (String) raw;
            int count = text.codePointCount(0, text.length());
            if (count > MAX_CHARS) throw new IllegalArgumentException("剪贴板文本不能超过 50000 字符");
            clipboard.setPrimaryClip(ClipData.newPlainText("MuseLite", text));
            // Android allows writes while backgrounded; do not read back and trigger a denied read.
            return new JSONObject().put("written", true).put("chars", count);
        }
        throw new IllegalArgumentException("未知剪贴板操作：" + action);
    }

    public static String call(Activity activity, String requestJson) {
        FutureTask<JSONObject> task = null;
        try {
            JSONObject request = new JSONObject(requestJson);
            String action = request.getString("action");
            JSONObject args = request.optJSONObject("params");
            final JSONObject input = args == null ? new JSONObject() : args;
            JSONObject result;
            if (Looper.myLooper() == Looper.getMainLooper()) result = perform(activity, action, input);
            else {
                task = new FutureTask<>(() -> perform(activity, action, input));
                activity.runOnUiThread(task);
                result = task.get(3, TimeUnit.SECONDS);
            }
            return new JSONObject().put("result", result).toString();
        } catch (Exception error) {
            if (task != null) task.cancel(false);
            Throwable cause = error.getCause() == null ? error : error.getCause();
            try { return new JSONObject().put("error", cause.getMessage() == null ? cause.toString() : cause.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"剪贴板操作失败\"}"; }
        }
    }
}
