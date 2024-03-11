# Traffic & WHOIS Bot

Simple telegram bot implemented in Python using aiogram and sanic.
The main purpose is to collect traffic usage data from several VPS and notify to Telegram when the daily limit is exceeded.
It is also possible to display daily statistics on a web page.

## Installation

1. Register two bots via @BotFather
2. Create *config_local.py* file
    
        VISITORS_BOT_TOKEN="0000000000:YourWHOISBotTokenHere"
        TRAFFIC_BOT_TOKEN="0000000000:YourTrafficBotTokenHere"
        TRAFFIC_URL_TOKEN="RandomString"

3. Adjust values in *visitors.py* file: DAILY_LIMIT (in bytes) and NOTIFY_PERCENT (%)

4. Add the following to the beginning of your nginx site config

        upstream whois {
            keepalive 100;
            server unix:/tmp/visitors.sanic;
        }


5. Add the following to your nginx site config inside *server* block

        location /a/ {
            proxy_pass http://whois;
            proxy_http_version 1.1;
            proxy_request_buffering off;
            proxy_buffering off;
            proxy_set_header forwarded "$proxy_forwarded;secret=\"ZDMBXTGGut01BaXGEc7e\"";
            proxy_set_header connection "upgrade";
            proxy_set_header upgrade $http_upgrade;
        }

6. Reload nginx

        sudo nginx -s reload

7. Execute (as non-root user, with sudo access)

        ./setup.sh

8. Your statistics page will be available at https://example.com/a/traffic

9. Add the following to /etc/crontab on each VPS

        0 *     * * *   root    curl "https://example.com/a/TRAFFIC_URL_TOKEN/hostname?rx=$(cat /sys/class/net/enp0s6/statistics/rx_bytes)&tx=$(cat /sys/class/net/enp0s6/statistics/tx_bytes)"

    Replace *TRAFFIC_URL_TOKEN* with value from config_local.py file, *hostname* with unique value for each VPS. You may also need to change *enp0s6* to correct network interface name (use "ip address" command to determine it)