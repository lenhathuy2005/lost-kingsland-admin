package com.lostkingsland.media;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

/**
 * HTTP alternative. Bot requests the image by item_code, not by a hand-entered URL or folder path.
 * This is useful before the bot is wired to platform.media_assets via JdbcTemplate.
 */
@Component
public class ItemMediaResolver {
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private final String adminBaseUrl;

    public ItemMediaResolver(@Value("${lost-kingsland.admin.base-url:http://127.0.0.1:8787}") String adminBaseUrl) {
        this.adminBaseUrl = adminBaseUrl.replaceAll("/+$", "");
    }

    public Optional<URI> resolveByItemCode(String itemCode) {
        if (itemCode == null || itemCode.isBlank()) return Optional.empty();
        String encoded = URLEncoder.encode(itemCode, StandardCharsets.UTF_8);
        return Optional.of(URI.create(adminBaseUrl + "/api/public/items/" + encoded + "/image"));
    }

    public Optional<byte[]> fetchBytesByItemCode(String itemCode) {
        try {
            Optional<URI> uri = resolveByItemCode(itemCode);
            if (uri.isEmpty()) return Optional.empty();
            HttpRequest request = HttpRequest.newBuilder(uri.get())
                    .timeout(Duration.ofSeconds(6))
                    .GET()
                    .build();
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() / 100 != 2) return Optional.empty();
            return Optional.of(response.body());
        } catch (Exception ignored) {
            return Optional.empty();
        }
    }
}
