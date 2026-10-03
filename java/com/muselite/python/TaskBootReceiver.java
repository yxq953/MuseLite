package com.muselite.python;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Restores enabled scheduled tasks after Android clears alarms on reboot. */
public final class TaskBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (intent != null && Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()))
            SessionAlarmScheduler.restoreTasks(context);
    }
}
