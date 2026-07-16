FROM wordpress:php8.3-apache

COPY wordpress-entrypoint.sh /usr/local/bin/wordpress-entrypoint.sh

RUN set -eux; \
  apt-get update; \
  apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ${PHPIZE_DEPS}; \
  pecl install redis; \
  docker-php-ext-enable redis; \
  mkdir -p /opt/wp-plugins; \
  curl -fsSL https://downloads.wordpress.org/plugin/redis-cache.2.8.0.zip -o /tmp/redis-cache.zip; \
  unzip -q /tmp/redis-cache.zip -d /opt/wp-plugins; \
  curl -fsSL https://downloads.wordpress.org/plugin/cache-enabler.latest-stable.zip -o /tmp/cache-enabler.zip; \
  unzip -q /tmp/cache-enabler.zip -d /opt/wp-plugins; \
  curl -fsSL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o /usr/local/bin/wp; \
  chmod +x /usr/local/bin/wp; \
  chmod +x /usr/local/bin/wordpress-entrypoint.sh; \
  rm -rf /tmp/* /var/lib/apt/lists/*; \
  a2enmod rewrite headers
