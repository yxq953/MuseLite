package com.muselite.python;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.provider.Settings;
import org.json.JSONObject;
import java.io.File;

/** JSON boundary for user-authorized phone control. */
public final class PhoneBridge {
    private static final String PREFS = "phone_control";
    private static final String ENABLED = "enabled";
    private PhoneBridge() {}

    static boolean enabled(Activity activity) {
        return activity.getSharedPreferences(PREFS, 0).getBoolean(ENABLED, false);
    }

    private static boolean notifications(Activity activity) {
        return Build.VERSION.SDK_INT < 33 ||
            activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }

    public static String status(Activity activity) {
        try {
            return new JSONObject().put("enabled", enabled(activity))
                .put("service", PhoneAccessibilityService.current() != null)
                .put("notifications", notifications(activity))
                .put("running", PhoneTaskService.running())
                .toString();
        } catch (Exception exc) { return "{}"; }
    }

    public static void setEnabled(Activity activity, boolean value) {
        activity.getSharedPreferences(PREFS, 0).edit().putBoolean(ENABLED, value).apply();
        if (!value) { ReplyHintBridge.close(); stopTask(activity); }
    }

    public static void openAccessibilitySettings(Activity activity) {
        activity.startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
    }

    public static void requestNotifications(Activity activity) {
        if (Build.VERSION.SDK_INT >= 33 && !notifications(activity))
            activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 7152);
    }

    public static void startTask(Activity activity) {
        if (!enabled(activity)) throw new IllegalStateException("请先开启应用内手机操作开关");
        if (PhoneAccessibilityService.current() == null)
            throw new IllegalStateException("请先在系统无障碍设置中启用 MuseLite Python");
        if (!notifications(activity)) throw new IllegalStateException("请先允许通知，再启动手机操作任务");
        PhoneTaskService.clearStop();
        Intent intent = new Intent(activity, PhoneTaskService.class);
        intent.setAction(PhoneTaskService.ACTION_START);
        try { activity.startForegroundService(intent); }
        catch (RuntimeException exc) { PhoneTaskService.requestStop(); throw exc; }
    }

    public static void stopTask(Activity activity) {
        PhoneTaskService.requestStop();
        activity.stopService(new Intent(activity, PhoneTaskService.class));
    }

    public static boolean stopRequested() { return PhoneTaskService.stopRequested(); }

    private static void guard(Activity activity) {
        if (!enabled(activity)) throw new IllegalStateException("手机操作已关闭");
        if (PhoneTaskService.stopRequested()) throw new IllegalStateException("手机操作任务已停止");
        if (!notifications(activity)) throw new IllegalStateException("通知权限已撤销，手机操作已停止");
        if (PhoneAccessibilityService.current() == null)
            throw new IllegalStateException("无障碍服务未运行；请检查系统设置");
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject request = new JSONObject(requestJson);
            String action = request.getString("action");
            JSONObject args = request.optJSONObject("params");
            if (args == null) args = new JSONObject();
            if (action.equals("status")) return new JSONObject().put("result", new JSONObject(status(activity))).toString();
            guard(activity);
            PhoneAccessibilityService service = PhoneAccessibilityService.current();
            JSONObject result;
            switch (action) {
                case "inspect": result = service.inspect(); break;
                case "read_chat":
                    int chatTimeout = args.optInt("timeout_ms", 30000);
                    if (chatTimeout < 200 || chatTimeout > 30000)
                        throw new IllegalArgumentException("timeout_ms 必须在 200 到 30000 之间");
                    String expectedPackage = args.optString("package_name", "");
                    if (activity.getPackageName().equals(expectedPackage))
                        throw new IllegalArgumentException("请指定外部聊天应用");
                    long chatDeadline = android.os.SystemClock.uptimeMillis() + chatTimeout;
                    JSONObject chat = null;
                    String reason = "请打开聊天界面";
                    while (android.os.SystemClock.uptimeMillis() < chatDeadline) {
                        guard(activity);
                        service = PhoneAccessibilityService.current();
                        try { chat = service.readChat(expectedPackage); break; }
                        catch (IllegalStateException unavailable) { reason = unavailable.getMessage(); }
                        Thread.sleep(200);
                    }
                    if (chat == null) throw new IllegalStateException("读取聊天界面超时：" + reason);
                    result = chat; break;
                case "screenshot":
                    result = service.screenshot(new File(activity.getCacheDir(), "phone-screenshots")); break;
                case "tap": result = service.tap(args, false); break;
                case "long_press": result = service.tap(args, true); break;
                case "type": result = service.type(args, false); break;
                case "clear": result = service.type(args, true); break;
                case "swipe": result = service.swipe(args); break;
                case "scroll": result = service.scroll(args); break;
                case "press": result = service.press(args.getString("key")); break;
                case "open_app":
                    String packageName = args.getString("package_name");
                    Intent launch = activity.getPackageManager().getLaunchIntentForPackage(packageName);
                    if (launch == null) throw new IllegalStateException("找不到可打开的应用：" + packageName);
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    activity.startActivity(launch);
                    result = new JSONObject().put("performed", true); break;
                case "wait":
                    int timeout = Math.max(200, Math.min(30000, args.optInt("timeout_ms", 10000)));
                    boolean present = args.optBoolean("present", true);
                    long deadline = android.os.SystemClock.uptimeMillis() + timeout;
                    boolean matched = false;
                    while (android.os.SystemClock.uptimeMillis() < deadline) {
                        guard(activity);
                        try { matched = service.hasTarget(args) == present; }
                        catch (IllegalStateException missingRoot) { matched = !present; }
                        if (matched) break;
                        Thread.sleep(200);
                    }
                    result = new JSONObject().put("matched", matched).put("timed_out", !matched); break;
                default: throw new IllegalArgumentException("不支持的手机操作：" + action);
            }
            guard(activity);
            return new JSONObject().put("result", result).toString();
        } catch (Exception exc) {
            try { return new JSONObject().put("error", exc.getMessage() == null ? exc.toString() : exc.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"phone bridge failure\"}"; }
        }
    }
}
