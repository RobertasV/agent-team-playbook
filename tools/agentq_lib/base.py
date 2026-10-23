"""Errors, time, short text helpers and the marks agentq leaves in GitHub comments."""

import datetime as dt
import os
import re

from .system import PACKAGE


TEMPLATE = os.path.join(PACKAGE, 'templates', 'dispatcher')
DEFAULT_CONFIG = os.path.expanduser('~/.config/agentq/config.json')
PROJECT_CONFIG = '.agentq.json'
FULL = 'Accept: application/vnd.github.full+json'
WAIT_MARK = re.compile(r'<!-- agentq:wait ([\w.-]+/[\w.-]+)#(\d+) -->')
ROUTE_MARK = '<!-- agentq:route -->'
CLAIM_MARK = re.compile(r'<!-- agentq:claim (\S+) -->')
BATCH_MARK = re.compile(r'<!-- agentq:batch (\{.*?\}) -->')
REF = re.compile(r'^(?:([\w.-]+/[\w.-]+)#)?#?(\d+)$')
ARROW = re.compile(r'\s*(?:→|->)\s*')

REPO_FILE = re.compile(r'^https://(?:github\.com/([\w.-]+)/([\w.-]+)/(?:raw|blob)/([^/]+)/([^?#]+)'
                       r'|raw\.githubusercontent\.com/([\w.-]+)/([\w.-]+)/([^/]+)/([^?#]+))')

# A file of a release, such as the margin-shots-N prerelease Margin keeps a project's screenshots in.
RELEASE_FILE = re.compile(r'^https://github\.com/([\w.-]+)/([\w.-]+)/releases/download/([^/]+)/([^/?#]+)$')

IMG = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.I)


class Fail(Exception):
    pass


def now():
    fixed = os.environ.get('AGENTQ_NOW')
    if fixed:
        return parse_time(fixed)
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def parse_time(text):
    return dt.datetime.fromisoformat(text.replace('Z', '+00:00'))


def iso(moment):
    return moment.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def number(text):
    value = float(text)
    return int(value) if value.is_integer() else value


def one_line(text, size=200):
    text = ' '.join(text.split())
    return text if len(text) <= size else text[:size - 1] + '…'
