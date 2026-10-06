package com.muselite.python;

import android.Manifest;
import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.CalendarContract;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

/** Small synchronous bridge for the Android system calendar provider. */
public final class CalendarBridge {
    private static final int REQUEST_CODE = 7412;
    private CalendarBridge() {}

    private static boolean readable(Activity a) {
        return a.checkSelfPermission(Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED;
    }
    private static boolean writable(Activity a) {
        return readable(a) && a.checkSelfPermission(Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED;
    }
    private static void require(Activity a, boolean write) {
        if (write ? writable(a) : readable(a)) return;
        List<String> missing = new ArrayList<>();
        if (!readable(a)) missing.add(Manifest.permission.READ_CALENDAR);
        if (write && a.checkSelfPermission(Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED)
            missing.add(Manifest.permission.WRITE_CALENDAR);
        a.requestPermissions(missing.toArray(new String[0]), REQUEST_CODE);
        throw new IllegalStateException("请允许 MuseLite 访问日历后重试");
    }

    public static String call(Activity activity, String requestJson) {
        try {
            JSONObject req = new JSONObject(requestJson);
            String action = req.optString("action", "");
            JSONObject p = req.optJSONObject("params");
            if (p == null) p = new JSONObject();
            boolean write = action.equals("create") || action.equals("update") || action.equals("delete");
            require(activity, write);
            ContentResolver cr = activity.getContentResolver();
            switch (action) {
                case "calendars": return ok(calendars(cr)).toString();
                case "list": return ok(list(cr, p)).toString();
                case "freebusy": return ok(freebusy(cr, p)).toString();
                case "create": return ok(create(cr, p)).toString();
                case "update": return ok(update(cr, p)).toString();
                case "delete":
                    int deleted = cr.delete(ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, p.getLong("id")), null, null);
                    if (deleted == 0) throw new IllegalArgumentException("事件不存在");
                    return ok(true).toString();
                default: throw new IllegalArgumentException("未知日历操作：" + action);
            }
        } catch (Exception e) {
            try { return new JSONObject().put("error", e.getMessage() == null ? e.toString() : e.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"calendar failure\"}"; }
        }
    }

    private static JSONObject ok(Object value) throws Exception { return new JSONObject().put("result", value); }

    private static JSONArray calendars(ContentResolver cr) throws Exception {
        JSONArray out = new JSONArray();
        try (Cursor c = cr.query(CalendarContract.Calendars.CONTENT_URI,
                new String[]{CalendarContract.Calendars._ID, CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
                    CalendarContract.Calendars.ACCOUNT_NAME, CalendarContract.Calendars.VISIBLE,
                    CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL}, null, null, "_id")) {
            if (c != null) while (c.moveToNext()) {
                JSONObject row = new JSONObject(); row.put("id", c.getLong(0));
                row.put("name", c.getString(1)); row.put("account", c.getString(2));
                row.put("visible", c.getInt(3) != 0); row.put("writable", c.getInt(4) >= CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR);
                out.put(row);
            }
        }
        return out;
    }

    private static JSONArray list(ContentResolver cr, JSONObject p) throws Exception {
        long start = p.optLong("start", System.currentTimeMillis());
        long end = p.optLong("end", start + 86400000L);
        String sel = "dtstart < ? AND dtend > ?";
        ArrayList<String> args = new ArrayList<>(); args.add(Long.toString(end)); args.add(Long.toString(start));
        if (p.has("calendar_id")) { sel += " AND calendar_id = ?"; args.add(Long.toString(p.getLong("calendar_id"))); }
        JSONArray out = new JSONArray();
        try (Cursor c = cr.query(CalendarContract.Events.CONTENT_URI, eventProjection(), sel,
                args.toArray(new String[0]), "dtstart ASC")) {
            if (c != null) while (c.moveToNext() && out.length() < p.optInt("limit", 100)) out.put(event(c));
        }
        return out;
    }

    private static JSONArray freebusy(ContentResolver cr, JSONObject p) throws Exception {
        JSONArray events = list(cr, p), out = new JSONArray();
        for (int i = 0; i < events.length(); i++) { JSONObject e = events.getJSONObject(i); out.put(new JSONObject().put("start", e.getLong("start")).put("end", e.getLong("end")).put("title", e.optString("title"))); }
        return out;
    }

    private static JSONObject create(ContentResolver cr, JSONObject p) throws Exception {
        ContentValues v = values(p, true);
        android.net.Uri uri = cr.insert(CalendarContract.Events.CONTENT_URI, v);
        if (uri == null) throw new IllegalStateException("创建日历事件失败");
        long id = ContentUris.parseId(uri);
        if (p.has("alarm")) { ContentValues r = new ContentValues(); r.put(CalendarContract.Reminders.EVENT_ID, id); r.put(CalendarContract.Reminders.MINUTES, p.getInt("alarm")); r.put(CalendarContract.Reminders.METHOD, CalendarContract.Reminders.METHOD_ALERT); cr.insert(CalendarContract.Reminders.CONTENT_URI, r); }
        return new JSONObject().put("id", id);
    }
    private static JSONObject update(ContentResolver cr, JSONObject p) throws Exception {
        long id=p.getLong("id");
        int changed = cr.update(ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI,id), values(p,false), null,null);
        if (changed == 0) throw new IllegalArgumentException("事件不存在");
        if (p.has("alarm")) {
            cr.delete(CalendarContract.Reminders.CONTENT_URI, CalendarContract.Reminders.EVENT_ID + "=?", new String[]{Long.toString(id)});
            if (!p.isNull("alarm")) {
                ContentValues r = new ContentValues(); r.put(CalendarContract.Reminders.EVENT_ID, id);
                r.put(CalendarContract.Reminders.MINUTES, p.getInt("alarm")); r.put(CalendarContract.Reminders.METHOD, CalendarContract.Reminders.METHOD_ALERT);
                cr.insert(CalendarContract.Reminders.CONTENT_URI, r);
            }
        }
        return new JSONObject().put("id",id);
    }
    private static ContentValues values(JSONObject p, boolean required) throws Exception {
        ContentValues v=new ContentValues(); if(required&&!p.has("title")) throw new IllegalArgumentException("title 为必填项"); if(required&&!p.has("start")) throw new IllegalArgumentException("start 为必填项");
        if(p.has("title"))v.put(CalendarContract.Events.TITLE,p.optString("title")); if(p.has("start"))v.put(CalendarContract.Events.DTSTART,p.getLong("start")); if(p.has("end"))v.put(CalendarContract.Events.DTEND,p.getLong("end")); else if(required)v.put(CalendarContract.Events.DTEND,p.getLong("start")+3600000L);
        if(p.has("notes"))v.put(CalendarContract.Events.DESCRIPTION,p.optString("notes")); if(p.has("location"))v.put(CalendarContract.Events.EVENT_LOCATION,p.optString("location")); if(p.has("all_day"))v.put(CalendarContract.Events.ALL_DAY,p.optBoolean("all_day")?1:0); if(p.has("calendar_id"))v.put(CalendarContract.Events.CALENDAR_ID,p.getLong("calendar_id")); if(required&&!p.has("calendar_id")) throw new IllegalArgumentException("calendar_id 为必填项"); v.put(CalendarContract.Events.EVENT_TIMEZONE, java.util.TimeZone.getDefault().getID()); return v;
    }
    private static String[] eventProjection(){return new String[]{CalendarContract.Events._ID,CalendarContract.Events.CALENDAR_ID,CalendarContract.Events.TITLE,CalendarContract.Events.DTSTART,CalendarContract.Events.DTEND,CalendarContract.Events.DESCRIPTION,CalendarContract.Events.EVENT_LOCATION,CalendarContract.Events.ALL_DAY};}
    private static JSONObject event(Cursor c)throws Exception{JSONObject e=new JSONObject();e.put("id",c.getLong(0));e.put("calendar_id",c.getLong(1));e.put("title",c.isNull(2)?"":c.getString(2));e.put("start",c.getLong(3));e.put("end",c.getLong(4));e.put("notes",c.isNull(5)?"":c.getString(5));e.put("location",c.isNull(6)?"":c.getString(6));e.put("all_day",c.getInt(7)!=0);return e;}
}
