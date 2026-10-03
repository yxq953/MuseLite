package com.muselite.python;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.content.SharedPreferences;

/** Schedules a durable Android alarm that reopens a saved conversation. */
public final class SessionAlarmScheduler {
    static final String ACTION = "com.muselite.python.OPEN_SESSION_ALARM";
    static final String EXTRA_SESSION_ID = "session_id";
    static final String EXTRA_REPEAT_DAILY = "repeat_daily";
    static final String EXTRA_PROMPT = "prompt";
    static final String EXTRA_TASK_ID = "task_id";
    private static final String TASK_PREFS = "scheduled_task_alarms";

    private SessionAlarmScheduler() {}

    public static void schedule(Context context, String sessionId, String prompt,
                                long whenMillis, boolean repeatDaily) {
        if (sessionId == null || sessionId.trim().isEmpty())
            throw new IllegalArgumentException("会话不存在");
        if (whenMillis <= System.currentTimeMillis())
            throw new IllegalArgumentException("请选择未来时间");
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) throw new IllegalStateException("系统闹钟不可用");
        PendingIntent pending = pendingIntent(context, sessionId, repeatDaily,
                                              prompt, PendingIntent.FLAG_UPDATE_CURRENT);
        if (repeatDaily) alarms.setInexactRepeating(AlarmManager.RTC_WAKEUP, whenMillis,
                AlarmManager.INTERVAL_DAY, pending);
        else if (Build.VERSION.SDK_INT >= 23)
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMillis, pending);
        else alarms.set(AlarmManager.RTC_WAKEUP, whenMillis, pending);
    }

    public static void cancel(Context context, String sessionId, String prompt, boolean repeatDaily) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        PendingIntent pending = pendingIntent(context, sessionId, repeatDaily, prompt,
                                              PendingIntent.FLAG_NO_CREATE);
        if (alarms != null && pending != null) alarms.cancel(pending);
        if (pending != null) pending.cancel();
    }

    public static void scheduleTask(Context context, String taskId, long whenMillis,
                                    boolean repeatDaily) {
        if (taskId == null || taskId.isEmpty()) throw new IllegalArgumentException("任务不存在");
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarms == null) throw new IllegalStateException("系统闹钟不可用");
        long when = repeatDaily ? nextDailyTime(whenMillis) : whenMillis;
        if (when <= System.currentTimeMillis()) throw new IllegalArgumentException("请选择未来时间");
        PendingIntent pending = taskPendingIntent(context, taskId, PendingIntent.FLAG_UPDATE_CURRENT);
        if (Build.VERSION.SDK_INT >= 31 && !alarms.canScheduleExactAlarms())
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pending);
        else if (Build.VERSION.SDK_INT >= 23)
            alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pending);
        else alarms.setExact(AlarmManager.RTC_WAKEUP, when, pending);
        context.getSharedPreferences(TASK_PREFS, Context.MODE_PRIVATE).edit()
                .putString(taskId, whenMillis + ":" + (repeatDaily ? "1" : "0")).apply();
    }

    public static void cancelTask(Context context, String taskId) {
        PendingIntent pending = taskPendingIntent(context, taskId, PendingIntent.FLAG_NO_CREATE);
        if (pending != null) {
            AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
            if (alarms != null) alarms.cancel(pending);
            pending.cancel();
        }
        context.getSharedPreferences(TASK_PREFS, Context.MODE_PRIVATE).edit()
                .remove(taskId).apply();
    }

    public static void markTaskFired(Context context, String taskId) {
        SharedPreferences prefs = context.getSharedPreferences(TASK_PREFS, Context.MODE_PRIVATE);
        String value = prefs.getString(taskId, "");
        if (value.endsWith(":0")) prefs.edit().remove(taskId).apply();
        else if (value.endsWith(":1")) {
            try { scheduleTask(context, taskId, Long.parseLong(value.split(":")[0]), true); }
            catch (Exception ignored) {}
        }
    }

    public static void restoreTasks(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(TASK_PREFS, Context.MODE_PRIVATE);
        for (java.util.Map.Entry<String, ?> entry : prefs.getAll().entrySet()) {
            try {
                String[] value = String.valueOf(entry.getValue()).split(":");
                long when = Long.parseLong(value[0]);
                boolean daily = value[1].equals("1");
                if (daily || when > System.currentTimeMillis())
                    scheduleTask(context, entry.getKey(), when, daily);
                else prefs.edit().remove(entry.getKey()).apply();
            } catch (Exception ignored) { prefs.edit().remove(entry.getKey()).apply(); }
        }
    }

    private static long nextDailyTime(long whenMillis) {
        java.util.Calendar selected = java.util.Calendar.getInstance();
        selected.setTimeInMillis(whenMillis);
        java.util.Calendar next = java.util.Calendar.getInstance();
        next.set(java.util.Calendar.HOUR_OF_DAY, selected.get(java.util.Calendar.HOUR_OF_DAY));
        next.set(java.util.Calendar.MINUTE, selected.get(java.util.Calendar.MINUTE));
        next.set(java.util.Calendar.SECOND, 0);
        next.set(java.util.Calendar.MILLISECOND, 0);
        if (next.getTimeInMillis() <= System.currentTimeMillis())
            next.add(java.util.Calendar.DAY_OF_MONTH, 1);
        return next.getTimeInMillis();
    }

    private static PendingIntent taskPendingIntent(Context context, String taskId, int flags) {
        Intent intent = new Intent(context, SessionAlarmReceiver.class).setAction(ACTION)
                .setData(android.net.Uri.parse("muselite://task/" + taskId))
                .putExtra(EXTRA_TASK_ID, taskId);
        return PendingIntent.getBroadcast(context, 0, intent, flags | PendingIntent.FLAG_IMMUTABLE);
    }

    private static PendingIntent pendingIntent(Context context, String sessionId,
                                               boolean repeatDaily, String prompt, int flags) {
        Intent intent = new Intent(context, SessionAlarmReceiver.class).setAction(ACTION)
                .putExtra(EXTRA_SESSION_ID, sessionId)
                .putExtra(EXTRA_PROMPT, prompt == null ? "" : prompt)
                .putExtra(EXTRA_REPEAT_DAILY, repeatDaily);
        int requestCode = Math.abs((sessionId + ":" + (prompt == null ? "" : prompt) +
                (repeatDaily ? ":daily" : ":once")).hashCode());
        return PendingIntent.getBroadcast(context, requestCode, intent,
                flags | PendingIntent.FLAG_IMMUTABLE);
    }
}
