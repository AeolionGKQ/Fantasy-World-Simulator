package com.fantasysimulator.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.util.Base64;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.json.JSONObject;

/** The WebView's way into the game backend (platform/native.ts), plus saving files the user picks. */
@CapacitorPlugin(name = "Backend")
public class BackendPlugin extends Plugin {

    @PluginMethod
    public void request(PluginCall call) {
        String method = call.getString("method", "GET");
        String path = call.getString("path", "");
        JSObject headers = call.getObject("headers", new JSObject());
        String body = call.getString("body");
        boolean queued = Backend.submit(() -> {
            byte[] bytes = body == null ? null : body.getBytes(StandardCharsets.UTF_8);
            call.resolve(toResult(Backend.call(method, path, headers, bytes)));
        });
        if (!queued) call.resolve(toResult(Backend.busy()));
    }

    private static JSObject toResult(Backend.Response response) {
        JSObject result = new JSObject();
        result.put("status", response.status);
        JSObject headers = new JSObject();
        for (java.util.Iterator<String> keys = response.headers.keys(); keys.hasNext(); ) {
            String key = keys.next();
            headers.put(key, response.headers.optString(key));
        }
        result.put("headers", headers);
        if (response.isText()) {
            result.put("body", new String(response.body, StandardCharsets.UTF_8));
        } else {
            result.put("bodyBase64", Base64.encodeToString(response.body, Base64.NO_WRAP));
        }
        return result;
    }

    /**
     * Saving a file is two calls: stageFile writes the base64 data to the cache and returns an id,
     * then saveFile opens the system picker with only that id. Capacitor keeps the picker call's
     * options in the activity's saved state, which Android caps at about 1 MB.
     */
    @PluginMethod
    public void stageFile(PluginCall call) {
        String data = call.getString("data");
        if (data == null) {
            call.reject("缺少文件内容");
            return;
        }
        boolean queued = Backend.submit(() -> {
            try {
                File folder = stagingFolder();
                File[] old = folder.listFiles();
                if (old != null) for (File file : old) file.delete();  // left by an earlier, abandoned save
                String id = UUID.randomUUID().toString();
                try (OutputStream output = new FileOutputStream(new File(folder, id))) {
                    output.write(Base64.decode(data, Base64.DEFAULT));
                }
                call.resolve(new JSObject().put("id", id));
            } catch (Exception error) {
                call.reject("保存文件失败", error);
            }
        });
        if (!queued) call.reject("保存文件失败：请求过多");
    }

    /** Ask the user where to save (system file picker), then copy the staged file there. */
    @PluginMethod
    public void saveFile(PluginCall call) {
        String filename = call.getString("filename", "download");
        String mimeType = call.getString("mimeType", "application/octet-stream");
        String id = call.getString("id", "");
        if (!id.matches("[0-9a-f-]{36}") || !new File(stagingFolder(), id).isFile()) {
            call.reject("缺少文件内容");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType(mimeType)
            .putExtra(Intent.EXTRA_TITLE, filename);
        startActivityForResult(call, intent, "saveFileResult");
    }

    @ActivityCallback
    private void saveFileResult(PluginCall call, ActivityResult result) {
        File staged = new File(stagingFolder(), call.getString("id", ""));
        Uri uri = result.getData() == null ? null : result.getData().getData();
        if (result.getResultCode() != Activity.RESULT_OK || uri == null) {
            staged.delete();
            call.resolve(new JSObject().put("saved", false));
            return;
        }
        boolean queued = Backend.submit(() -> {
            try (InputStream input = new FileInputStream(staged);
                 OutputStream output = getContext().getContentResolver().openOutputStream(uri, "wt")) {
                if (output == null) throw new java.io.IOException("no output stream");
                byte[] buffer = new byte[65536];
                for (int read; (read = input.read(buffer)) > 0; ) output.write(buffer, 0, read);
                call.resolve(new JSObject().put("saved", true));
            } catch (Exception error) {
                call.reject("保存文件失败", error);
            } finally {
                staged.delete();
            }
        });
        if (!queued) call.reject("保存文件失败：请求过多");
    }

    private File stagingFolder() {
        File folder = new File(getContext().getCacheDir(), "outgoing-files");
        folder.mkdirs();
        return folder;
    }
}
