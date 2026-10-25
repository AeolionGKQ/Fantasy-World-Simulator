package com.fantasysimulator.app;

import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.ByteArrayInputStream;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import org.json.JSONObject;

/**
 * Answers GET /api/... loads that do not go through fetch, such as <img src> for scene images,
 * straight from the backend. Everything else is Capacitor's usual local asset server.
 */
public class BackendWebViewClient extends BridgeWebViewClient {

    private final Bridge bridge;

    public BackendWebViewClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        String path = url.getPath();
        if ("GET".equals(request.getMethod()) && path != null && path.startsWith("/api/") && isAppOrigin(url)) {
            String query = url.getEncodedQuery();
            String target = url.getEncodedPath() + (query == null ? "" : "?" + query);
            JSONObject headers = new JSONObject();
            Backend.Response response = Backend.call("GET", target, headers, null);
            Map<String, String> responseHeaders = new HashMap<>();
            for (Iterator<String> keys = response.headers.keys(); keys.hasNext(); ) {
                String key = keys.next();
                if (!key.equalsIgnoreCase("Content-Type")) responseHeaders.put(key, response.headers.optString(key));
            }
            String charset = response.isText() ? "utf-8" : null;
            return new WebResourceResponse(
                response.contentType(), charset, response.status, reason(response.status),
                responseHeaders, new ByteArrayInputStream(response.body)
            );
        }
        return super.shouldInterceptRequest(view, request);
    }

    private boolean isAppOrigin(Uri url) {
        Uri app = Uri.parse(bridge.getAppUrl());
        return app.getHost() != null && app.getHost().equals(url.getHost());
    }

    private static String reason(int status) {
        if (status < 300) return "OK";
        if (status == 404) return "Not Found";
        if (status < 500) return "Client Error";
        return "Server Error";
    }
}
