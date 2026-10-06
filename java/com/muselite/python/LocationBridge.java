package com.muselite.python;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationManager;
import android.os.CancellationSignal;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/** One-shot bridge for the Android system location providers. */
public final class LocationBridge {
    private static final int REQUEST_CODE = 7413;
    private LocationBridge() {}

    private static boolean fine(Activity a) {
        return a.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }
    private static boolean coarse(Activity a) {
        return a.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }
    private static void require(Activity a) {
        if (fine(a) || coarse(a)) return;
        List<String> missing = new ArrayList<>();
        missing.add(Manifest.permission.ACCESS_FINE_LOCATION);
        missing.add(Manifest.permission.ACCESS_COARSE_LOCATION);
        a.requestPermissions(missing.toArray(new String[0]), REQUEST_CODE);
        throw new IllegalStateException("请允许 MuseLite 访问位置信息后重试");
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject req = new JSONObject(requestJson);
            String action = req.optString("action", "get");
            if (!"get".equals(action)) throw new IllegalArgumentException("未知位置操作：" + action);
            require(activity);
            Location location = lastKnown(activity);
            String source = "last_known";
            if (location == null) {
                location = current(activity);
                source = "current";
            }
            if (location == null) throw new IllegalStateException("暂时无法获取当前位置，请确认定位服务已开启后重试");
            return new JSONObject().put("result", result(location, source)).toString();
        } catch (Exception e) {
            try { return new JSONObject().put("error", e.getMessage() == null ? e.toString() : e.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"location failure\"}"; }
        }
    }

    private static Location current(Activity activity) throws InterruptedException {
        LocationManager manager = (LocationManager) activity.getSystemService(Activity.LOCATION_SERVICE);
        if (manager == null) return null;
        String provider = null;
        try {
            if (manager.isProviderEnabled(LocationManager.GPS_PROVIDER)) provider = LocationManager.GPS_PROVIDER;
        } catch (Exception ignored) {}
        if (provider == null) {
            try {
                if (manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) provider = LocationManager.NETWORK_PROVIDER;
            } catch (Exception ignored) {}
        }
        if (provider == null) return null;
        CountDownLatch latch = new CountDownLatch(1);
        Location[] result = new Location[1];
        CancellationSignal signal = new CancellationSignal();
        final String selected = provider;
        Consumer<Location> callback = value -> { result[0] = value; latch.countDown(); };
        try {
            manager.getCurrentLocation(selected, signal, activity.getMainExecutor(), callback);
            latch.await(12, TimeUnit.SECONDS);
        } finally {
            signal.cancel();
        }
        return result[0];
    }

    /** Return the freshest cached location from any enabled system provider. */
    private static Location lastKnown(Activity activity) {
        LocationManager manager = (LocationManager) activity.getSystemService(Activity.LOCATION_SERVICE);
        if (manager == null) return null;
        Location best = null;
        for (String provider : new String[]{LocationManager.GPS_PROVIDER,
                LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER}) {
            try {
                Location candidate = manager.getLastKnownLocation(provider);
                if (candidate != null && (best == null || candidate.getTime() > best.getTime())) best = candidate;
            } catch (SecurityException ignored) {}
        }
        return best;
    }

    private static JSONObject result(Location location, String source) throws Exception {
        JSONObject out = new JSONObject();
        out.put("latitude", location.getLatitude());
        out.put("longitude", location.getLongitude());
        out.put("accuracy_m", location.hasAccuracy() ? location.getAccuracy() : JSONObject.NULL);
        out.put("altitude_m", location.hasAltitude() ? location.getAltitude() : JSONObject.NULL);
        out.put("speed_mps", location.hasSpeed() ? location.getSpeed() : JSONObject.NULL);
        out.put("bearing_deg", location.hasBearing() ? location.getBearing() : JSONObject.NULL);
        out.put("timestamp_ms", location.getTime());
        out.put("provider", location.getProvider());
        out.put("source", source);
        out.put("age_ms", Math.max(0L, System.currentTimeMillis() - location.getTime()));
        return out;
    }
}
