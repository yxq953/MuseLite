package com.muselite.python;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Alarm entry point. Launching the main activity lets the existing Python UI open the session. */
public final class SessionAlarmReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !SessionAlarmScheduler.ACTION.equals(intent.getAction())) return;
        String sessionId = intent.getStringExtra(SessionAlarmScheduler.EXTRA_SESSION_ID);
        String prompt = intent.getStringExtra(SessionAlarmScheduler.EXTRA_PROMPT);
        if (sessionId == null || sessionId.isEmpty()) return;
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        if (launch == null) return;
        launch.putExtra(SessionAlarmScheduler.EXTRA_SESSION_ID, sessionId);
        launch.putExtra(SessionAlarmScheduler.EXTRA_PROMPT, prompt == null ? "" : prompt);
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP |
                        Intent.FLAG_ACTIVITY_CLEAR_TOP);
        context.startActivity(launch);
    }
}
