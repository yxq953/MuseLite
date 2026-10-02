package com.muselite.python;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/** Schedules a durable Android alarm that reopens a saved conversation. */
public final class SessionAlarmScheduler {
    static final String ACTION = "com.muselite.python.OPEN_SESSION_ALARM";
    static final String EXTRA_SESSION_ID = "session_id";
    static final String EXTRA_REPEAT_DAILY = "repeat_daily";
    static final String EXTRA_PROMPT = "prompt";

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
        if (alarms != null) alarms.cancel(pendingIntent(context, sessionId, repeatDaily, prompt,
                                                         PendingIntent.FLAG_NO_CREATE));
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
