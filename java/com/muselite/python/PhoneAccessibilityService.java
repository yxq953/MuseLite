package com.muselite.python;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Bitmap;
import android.graphics.Path;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/** User-enabled service for the focused phone_use interaction API. */
public final class PhoneAccessibilityService extends AccessibilityService {
    private static volatile PhoneAccessibilityService instance;
    private final AtomicLong generation = new AtomicLong();
    private final Map<Integer, AccessibilityNodeInfo> snapshot = new HashMap<>();
    private long snapshotGeneration = -1;

    static PhoneAccessibilityService current() { return instance; }

    @Override protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        generation.incrementAndGet();
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event != null) generation.incrementAndGet();
    }

    @Override public void onInterrupt() { generation.incrementAndGet(); }

    @Override public void onDestroy() {
        if (instance == this) instance = null;
        synchronized (snapshot) { snapshot.clear(); snapshotGeneration = -1; }
        super.onDestroy();
    }

    private AccessibilityNodeInfo root() {
        AccessibilityNodeInfo value = getRootInActiveWindow();
        if (value == null) throw new IllegalStateException("当前界面不可读取；请解锁屏幕或切换应用");
        return value;
    }

    JSONObject inspect() throws Exception {
        long version = generation.get();
        JSONArray nodes = new JSONArray();
        Map<Integer, AccessibilityNodeInfo> current = new HashMap<>();
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>();
        queue.add(root());
        while (!queue.isEmpty() && nodes.length() < 500) {
            AccessibilityNodeInfo node = queue.removeFirst();
            int id = nodes.length() + 1;
            current.put(id, node);
            Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
            JSONObject item = new JSONObject();
            item.put("id", id);
            item.put("text", value(node.getText()));
            item.put("description", value(node.getContentDescription()));
            item.put("resource_id", value(node.getViewIdResourceName()));
            item.put("class", value(node.getClassName()));
            item.put("bounds", rect(bounds));
            item.put("clickable", node.isClickable());
            item.put("editable", node.isEditable());
            item.put("scrollable", node.isScrollable());
            nodes.put(item);
            for (int i = 0; i < node.getChildCount(); i++) {
                AccessibilityNodeInfo child = node.getChild(i);
                if (child != null) queue.addLast(child);
            }
        }
        if (generation.get() != version) throw new IllegalStateException("界面正在变化，请重试 inspect");
        synchronized (snapshot) {
            snapshot.clear(); snapshot.putAll(current); snapshotGeneration = version;
        }
        JSONObject output = new JSONObject();
        output.put("generation", version);
        output.put("package", value(root().getPackageName()));
        output.put("nodes", nodes);
        output.put("truncated", !queue.isEmpty());
        return output;
    }

    private static String value(CharSequence text) { return text == null ? "" : text.toString(); }
    private static JSONObject rect(Rect value) throws Exception {
        return new JSONObject().put("left", value.left).put("top", value.top)
            .put("right", value.right).put("bottom", value.bottom);
    }

    private AccessibilityNodeInfo find(JSONObject args) throws Exception {
        if (args.has("node_id")) {
            long requested = args.getLong("generation");
            synchronized (snapshot) {
                if (requested != snapshotGeneration || requested != generation.get())
                    throw new IllegalStateException("节点编号已过期，请重新 inspect");
                AccessibilityNodeInfo node = snapshot.get(args.getInt("node_id"));
                if (node == null) throw new IllegalArgumentException("节点编号不存在");
                return node;
            }
        }
        String text = args.optString("text", "");
        String resource = args.optString("resource_id", "");
        if (text.isEmpty() && resource.isEmpty()) throw new IllegalArgumentException("需要 node_id、text 或 resource_id");
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>(); queue.add(root());
        int visited = 0;
        while (!queue.isEmpty() && visited++ < 500) {
            AccessibilityNodeInfo node = queue.removeFirst();
            boolean match = !text.isEmpty() && (text.equals(value(node.getText())) ||
                text.equals(value(node.getContentDescription())));
            match |= !resource.isEmpty() && resource.equals(value(node.getViewIdResourceName()));
            if (match) return node;
            for (int i = 0; i < node.getChildCount(); i++) {
                AccessibilityNodeInfo child = node.getChild(i);
                if (child != null) queue.addLast(child);
            }
        }
        return null;
    }

    JSONObject tap(JSONObject args, boolean longPress) throws Exception {
        if (args.has("x") && args.has("y")) {
            gesture(args.getInt("x"), args.getInt("y"), args.getInt("x"), args.getInt("y"),
                longPress ? 750 : 90);
            return new JSONObject().put("performed", true);
        }
        AccessibilityNodeInfo node = find(args);
        if (node == null) throw new IllegalStateException("未找到目标");
        AccessibilityNodeInfo clickable = node;
        int action = longPress ? AccessibilityNodeInfo.ACTION_LONG_CLICK : AccessibilityNodeInfo.ACTION_CLICK;
        while (clickable != null) {
            if (clickable.performAction(action)) return new JSONObject().put("performed", true);
            clickable = clickable.getParent();
        }
        Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
        if (bounds.isEmpty()) throw new IllegalStateException("目标没有可点击区域");
        gesture(bounds.centerX(), bounds.centerY(), bounds.centerX(), bounds.centerY(), longPress ? 750 : 90);
        return new JSONObject().put("performed", true).put("fallback", "coordinates");
    }

    JSONObject type(JSONObject args, boolean clear) throws Exception {
        AccessibilityNodeInfo node = null;
        if (args.has("node_id") || args.has("resource_id")) node = find(args);
        if (node == null) node = root().findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (node == null || !node.isEditable()) throw new IllegalStateException("没有可编辑的输入框");
        Bundle data = new Bundle();
        data.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
            clear ? "" : args.getString("value"));
        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, data))
            throw new IllegalStateException("输入框拒绝设置文本");
        return new JSONObject().put("performed", true);
    }

    JSONObject swipe(JSONObject args) throws Exception {
        int duration = Math.max(100, Math.min(3000, args.optInt("duration_ms", 400)));
        gesture(args.getInt("x"), args.getInt("y"), args.getInt("end_x"), args.getInt("end_y"), duration);
        return new JSONObject().put("performed", true);
    }

    JSONObject scroll(JSONObject args) throws Exception {
        String direction = args.optString("direction", "down");
        int action = direction.equals("up") ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD :
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
        if (!direction.equals("up") && !direction.equals("down"))
            throw new IllegalArgumentException("direction 只支持 up/down");
        AccessibilityNodeInfo node = args.has("node_id") || args.has("resource_id") ? find(args) : root();
        while (node != null) {
            if (node.performAction(action)) return new JSONObject().put("performed", true);
            node = node.getParent();
        }
        android.util.DisplayMetrics metrics = getResources().getDisplayMetrics();
        int mid = metrics.widthPixels / 2;
        int top = metrics.heightPixels / 4, bottom = metrics.heightPixels * 3 / 4;
        gesture(mid, direction.equals("down") ? bottom : top, mid,
            direction.equals("down") ? top : bottom, 400);
        return new JSONObject().put("performed", true).put("fallback", "swipe");
    }

    JSONObject press(String key) throws Exception {
        int action;
        switch (key) {
            case "back": action = GLOBAL_ACTION_BACK; break;
            case "home": action = GLOBAL_ACTION_HOME; break;
            case "recents": action = GLOBAL_ACTION_RECENTS; break;
            default: throw new IllegalArgumentException("不支持的系统按键");
        }
        if (!performGlobalAction(action)) throw new IllegalStateException("系统按键操作失败");
        return new JSONObject().put("performed", true);
    }

    JSONObject screenshot(File directory) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        final Bitmap[] image = new Bitmap[1]; final int[] failure = new int[1];
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult result) {
                HardwareBuffer buffer = result.getHardwareBuffer();
                try { image[0] = Bitmap.wrapHardwareBuffer(buffer, result.getColorSpace()); }
                finally { buffer.close(); latch.countDown(); }
            }
            @Override public void onFailure(int code) { failure[0] = code; latch.countDown(); }
        });
        if (!latch.await(12, TimeUnit.SECONDS)) throw new IllegalStateException("截图超时");
        if (image[0] == null) throw new IllegalStateException("截图失败，错误码 " + failure[0] + "；页面可能禁止截图");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new IllegalStateException("截图目录不可写");
        Bitmap bitmap = image[0].copy(Bitmap.Config.ARGB_8888, false);
        if (bitmap == null) throw new IllegalStateException("截图无法转换为位图");
        int originalWidth = bitmap.getWidth(), originalHeight = bitmap.getHeight();
        if (bitmap.getWidth() > 1280) {
            bitmap = Bitmap.createScaledBitmap(bitmap, 1280,
                Math.max(1, bitmap.getHeight() * 1280 / bitmap.getWidth()), true);
        }
        File file = File.createTempFile("phone-", ".jpg", directory);
        try (FileOutputStream output = new FileOutputStream(file)) {
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, 82, output))
                throw new IllegalStateException("截图编码失败");
        }
        return new JSONObject().put("path", file.getAbsolutePath()).put("mime", "image/jpeg")
            .put("width", bitmap.getWidth()).put("height", bitmap.getHeight())
            .put("original_width", originalWidth).put("original_height", originalHeight);
    }

    private void gesture(int x, int y, int endX, int endY, int duration) throws Exception {
        android.util.DisplayMetrics screen = getResources().getDisplayMetrics();
        if (x < 0 || y < 0 || endX < 0 || endY < 0 || x >= screen.widthPixels ||
            endX >= screen.widthPixels || y >= screen.heightPixels || endY >= screen.heightPixels)
            throw new IllegalArgumentException("坐标超出屏幕范围");
        Path path = new Path(); path.moveTo(x, y); path.lineTo(endX, endY);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(
            new GestureDescription.StrokeDescription(path, 0, duration)).build();
        CountDownLatch latch = new CountDownLatch(1);
        final boolean[] completed = new boolean[1];
        if (!dispatchGesture(gesture, new GestureResultCallback() {
            @Override public void onCompleted(GestureDescription value) { completed[0] = true; latch.countDown(); }
            @Override public void onCancelled(GestureDescription value) { latch.countDown(); }
        }, new Handler(Looper.getMainLooper()))) throw new IllegalStateException("系统拒绝执行手势");
        if (!latch.await(8, TimeUnit.SECONDS)) throw new IllegalStateException("手势超时");
        if (!completed[0]) throw new IllegalStateException("手势已取消");
    }

    boolean hasTarget(JSONObject args) throws Exception { return find(args) != null; }
}
