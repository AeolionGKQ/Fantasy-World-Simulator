package com.fantasysimulator.app;

import android.Manifest;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Python starts in the background while the WebView loads; API calls wait for it.
        Backend.start(this);
        registerPlugin(BackendPlugin.class);
        super.onCreate(savedInstanceState);
        bridge.setWebViewClient(new BackendWebViewClient(bridge));
        askForNotificationsOnce();
    }

    /** The "story is being generated" notification needs this on Android 13+; asked only once. */
    private void askForNotificationsOnce() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return;
        SharedPreferences preferences = getSharedPreferences("app", MODE_PRIVATE);
        if (preferences.getBoolean("asked_notifications", false)) return;
        preferences.edit().putBoolean("asked_notifications", true).apply();
        ActivityCompat.requestPermissions(this, new String[] { Manifest.permission.POST_NOTIFICATIONS }, 1);
    }
}
