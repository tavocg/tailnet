#!/usr/bin/env bash
set -euo pipefail

if [ ! -e /var/www/html/index.php ] && [ -d /usr/src/wordpress ]; then
  cp -a /usr/src/wordpress/. /var/www/html/
  chown -R www-data:www-data /var/www/html
fi

mkdir -p \
  /var/www/html/wp-content/plugins \
  /var/www/html/wp-content/mu-plugins \
  /var/www/html/wp-content/cache/cache-enabler \
  /var/www/html/wp-content/settings/cache-enabler

if [ ! -d /var/www/html/wp-content/plugins/redis-cache ]; then
  cp -a /opt/wp-plugins/redis-cache /var/www/html/wp-content/plugins/redis-cache
fi

if [ ! -d /var/www/html/wp-content/plugins/cache-enabler ]; then
  cp -a /opt/wp-plugins/cache-enabler /var/www/html/wp-content/plugins/cache-enabler
fi

if [ -f /var/www/html/wp-content/plugins/redis-cache/includes/object-cache.php ]; then
  cp /var/www/html/wp-content/plugins/redis-cache/includes/object-cache.php /var/www/html/wp-content/object-cache.php
fi

cat > /var/www/html/wp-content/mu-plugins/cache-headers.php <<'PHP'
<?php
add_action('init', function () {
    $directories = [
        WP_CONTENT_DIR . '/cache/cache-enabler',
        WP_CONTENT_DIR . '/settings/cache-enabler',
    ];

    foreach ($directories as $directory) {
        if (! is_dir($directory)) {
            wp_mkdir_p($directory);
        }

        if (is_dir($directory) && ! is_writable($directory)) {
            @chmod($directory, 0755);
        }
    }
}, 1);

add_action('send_headers', function () {
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    if (! in_array($method, ['GET', 'HEAD'], true)) {
        return;
    }

    if (
        is_admin()
        || is_user_logged_in()
        || wp_doing_ajax()
        || wp_doing_cron()
        || (defined('REST_REQUEST') && REST_REQUEST)
        || is_preview()
        || is_search()
        || is_404()
    ) {
        return;
    }

    header('Cache-Control: public, max-age=300, stale-while-revalidate=60');
    header('X-Cache-Enabled: wordpress');
});
PHP

cat > /var/www/html/wp-content/mu-plugins/mailgun.php <<'PHP'
<?php
$mailgun_from_email = static function (): string {
    return getenv('MAILGUN_FROM_EMAIL') ?: sprintf('noreply@%s', getenv('WORDPRESS_DOMAIN') ?: 'example.com');
};

$mailgun_from_name = static function (): string {
    return getenv('MAILGUN_FROM_NAME') ?: (getenv('WORDPRESS_SITE_NAME') ?: 'WordPress');
};

$mailgun_domain = static function () use ($mailgun_from_email): string {
    $domain = getenv('MAILGUN_DOMAIN');
    if ($domain) {
        return $domain;
    }

    $from = $mailgun_from_email();
    return substr(strrchr($from, '@') ?: '@example.com', 1);
};

$mailgun_endpoint = static function (): string {
    return rtrim(getenv('MAILGUN_ENDPOINT') ?: 'https://api.mailgun.net', '/');
};

$parse_mail_headers = static function ($headers): array {
    $parsed = [
        'content_type' => 'text/plain',
        'from' => null,
        'reply_to' => null,
        'cc' => [],
        'bcc' => [],
    ];

    if (empty($headers)) {
        return $parsed;
    }

    if (! is_array($headers)) {
        $headers = explode("\n", str_replace("\r\n", "\n", (string) $headers));
    }

    foreach ($headers as $header) {
        if (! is_string($header) || strpos($header, ':') === false) {
            continue;
        }

        [$name, $value] = array_map('trim', explode(':', $header, 2));
        $name = strtolower($name);

        if ($name === 'content-type') {
            $parsed['content_type'] = strtolower(strtok($value, ';') ?: 'text/plain');
        } elseif ($name === 'from') {
            $parsed['from'] = $value;
        } elseif ($name === 'reply-to') {
            $parsed['reply_to'] = $value;
        } elseif ($name === 'cc') {
            $parsed['cc'][] = $value;
        } elseif ($name === 'bcc') {
            $parsed['bcc'][] = $value;
        }
    }

    return $parsed;
};

$mailgun_default_from = static function () use ($mailgun_from_name, $mailgun_from_email): string {
    return sprintf('%s <%s>', $mailgun_from_name(), $mailgun_from_email());
};

add_filter('wp_mail_from', $mailgun_from_email);
add_filter('wp_mail_from_name', $mailgun_from_name);

add_filter('pre_wp_mail', function ($return, $atts) use (
    $parse_mail_headers,
    $mailgun_default_from,
    $mailgun_endpoint,
    $mailgun_domain
) {
    $api_key = getenv('MAILGUN_API_KEY');
    if (! $api_key) {
        return null;
    }

    $headers = $parse_mail_headers($atts['headers'] ?? []);
    $to = $atts['to'] ?? [];
    $to = is_array($to) ? implode(', ', $to) : (string) $to;
    $subject = (string) ($atts['subject'] ?? '');
    $message = (string) ($atts['message'] ?? '');
    $attachments = $atts['attachments'] ?? [];

    if (! empty($attachments)) {
        error_log('Mailgun API mailer: attachments are not supported by this lightweight wp_mail transport.');
    }

    $body = [
        'from' => $headers['from'] ?: $mailgun_default_from(),
        'to' => $to,
        'subject' => $subject,
    ];

    if ($headers['content_type'] === 'text/html') {
        $body['html'] = $message;
    } else {
        $body['text'] = wp_strip_all_tags($message, false);
    }

    if ($headers['reply_to']) {
        $body['h:Reply-To'] = $headers['reply_to'];
    }

    if (! empty($headers['cc'])) {
        $body['cc'] = implode(', ', $headers['cc']);
    }

    if (! empty($headers['bcc'])) {
        $body['bcc'] = implode(', ', $headers['bcc']);
    }

    $url = sprintf(
        '%s/v3/%s/messages',
        $mailgun_endpoint(),
        rawurlencode($mailgun_domain())
    );

    $response = wp_remote_post($url, [
        'timeout' => 15,
        'headers' => [
            'Authorization' => 'Basic ' . base64_encode('api:' . $api_key),
        ],
        'body' => $body,
    ]);

    if (is_wp_error($response)) {
        error_log('Mailgun API mailer error: ' . $response->get_error_message());
        return false;
    }

    $status = (int) wp_remote_retrieve_response_code($response);
    if ($status < 200 || $status >= 300) {
        error_log(sprintf(
            'Mailgun API mailer failed with HTTP %d: %s',
            $status,
            wp_remote_retrieve_body($response)
        ));
        return false;
    }

    return true;
}, 10, 2);
PHP

chown -R www-data:www-data \
  /var/www/html/wp-content/cache \
  /var/www/html/wp-content/settings \
  /var/www/html/wp-content/plugins/redis-cache \
  /var/www/html/wp-content/plugins/cache-enabler \
  /var/www/html/wp-content/mu-plugins

activate_wordpress_plugins() {
  for _ in $(seq 1 120); do
    if wp core is-installed --allow-root --path=/var/www/html >/dev/null 2>&1; then
      wp plugin activate redis-cache --allow-root --path=/var/www/html || true
      wp redis enable --allow-root --path=/var/www/html || true
      wp plugin activate cache-enabler --allow-root --path=/var/www/html || true
      return
    fi

    sleep 10
  done
}

activate_wordpress_plugins &

exec docker-entrypoint.sh "$@"
