#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# coding=utf-8
import json
import logging
import os
import signal
import sys
import time

import facebook
import requests
import yaml

CONFIG_FILE = "matterbook.yml"
DATA_DIR = 'data'
FB_API_VERSION = '2.7'

log = logging.getLogger(__name__)


def main():
    setup_logging()
    log.info("Matterbook started")
    install_interrupt_handler()
    config = load_config()
    graph = get_graph_api(config)
    while True:
        try:
            check_posts(graph, config)
        except Exception as e:
            log.error("Unexpected error: %s", e.message)
        time.sleep(10)



def load_config():
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
    log.debug("Config loaded")
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False)
    log.debug("Config saved")
    return config


def check_posts(graph, config):
    mm_config = config['mattermost']
    integrations = config['integrations']
    for integration_entry in integrations:
        integration_id = integration_entry.keys()[0]
        integration = integration_entry[integration_id]
        log.info("Checking: %s" % integration_id)
        page_id = integration['fb_page_id']
        posts = graph.get_object(id=('%s/feed?fields=message,created_time,id&limit=1' % page_id))
        last_post = posts[u'data'][0]
        last_post_text = last_post.get('message', "").encode("utf8")
        post_filter = integration.get('fb_post_filter')
        if post_filter is None or post_filter.encode("utf8") in last_post_text:
            if last_post == load_last_saved_post(integration_id):
                log.debug("Old post: " + last_post_text)
            else:
                log.info("New post: " + last_post_text)
                username = integration.get('mm_username')
                icon_url = integration.get('mm_icon_url')
                basic_auth = mm_config.get('basic_auth')
                data = json.dumps({'username': username, 'text': last_post_text, 'icon_url': icon_url})
                webhook_url = mm_config['webhook_url']
                requests.post(webhook_url, data=data, auth=to_tuple(basic_auth))
                save_last_post(integration_id, last_post)
        else:
            log.info("Ignoring: " + last_post_text)


def to_tuple(basic_auth):
    return tuple(basic_auth.values()) if basic_auth is not None else None


def save_last_post(integration_id, post):
    ensure_data_dir_exists()
    with open(get_last_post_filename(integration_id), 'w') as f:
        json.dump(post, f)


def get_last_post_filename(integration_id):
    return os.path.join(DATA_DIR, "last_post_%s.json" % integration_id)


def ensure_data_dir_exists():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def load_last_saved_post(integration_id):
    ensure_data_dir_exists()
    if os.path.isfile(get_last_post_filename(integration_id)):
        with open(get_last_post_filename(integration_id), 'r') as f:
            last_post = json.load(f)
    else:
        last_post = dict()
    return last_post


def get_graph_api(config):
    extended_token = get_extended_token(config)
    graph = facebook.GraphAPI(access_token=extended_token, version=FB_API_VERSION)
    return graph


def get_extended_token(config):
    fb_config = config['facebook']
    access_token = fb_config['access_token']
    app_id = fb_config['app_id']
    app_secret = fb_config['app_secret']
    graph = facebook.GraphAPI(access_token=access_token, version=FB_API_VERSION)
    extended_token_data = graph.extend_access_token(app_id, app_secret)
    extended_token = extended_token_data['access_token']
    fb_config['access_token'] = extended_token
    save_config(config)
    return extended_token


def install_interrupt_handler():
    signal.signal(signal.SIGINT, signal_handler)
    log.info('Press Ctrl+C or send SIGINT to exit')


def signal_handler(sig, frame):
    log.info('SIGINT received! Bye!')
    sys.exit(0)


def setup_logging():
    logging.basicConfig(format='%(asctime)s [%(module)s] %(message)s')
    log.setLevel(logging.INFO)


main()
