# -*- coding: utf-8 -*-
"""
HidenCloud Auto Renew - Python Full Log Push Version
"""
import os
import sys
import time
import json
import random
import re
import requests
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from notify import send_notify
try:
    from cookie_context import normalize_cookie_records, parse_seed_cookie_string, success_path_label
except ModuleNotFoundError:
    DEFAULT_COOKIE_DOMAIN = '.dash.hidencloud.com'
    COOKIE_DOMAIN_OVERRIDES = {
        'cf_clearance': '.hidencloud.com',
    }
    CRITICAL_COOKIE_NAMES = {
        'XSRF-TOKEN',
        'hidencloud_session',
        'cf_clearance',
        'hc_cf_turnstile',
    }
    CRITICAL_COOKIE_PREFIXES = (
        'remember_web_',
    )

    def _domain_for_cookie(name):
        return COOKIE_DOMAIN_OVERRIDES.get(name, DEFAULT_COOKIE_DOMAIN)

    def _is_critical_cookie_name(name):
        if name in CRITICAL_COOKIE_NAMES:
            return True
        return any(name.startswith(prefix) for prefix in CRITICAL_COOKIE_PREFIXES)

    def parse_seed_cookie_string(cookie_str):
        deduped = {}
        for item in cookie_str.split(';'):
            if '=' not in item:
                continue
            name, value = item.split('=', 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            deduped[name] = {
                'name': name,
                'value': value,
                'domain': _domain_for_cookie(name),
                'path': '/',
                'secure': True,
            }
        return list(deduped.values())

    def _cookie_score(record):
        name = str(record.get('name') or '')
        domain = str(record.get('domain') or '')
        path = str(record.get('path') or '/')
        secure = 1 if record.get('secure') else 0
        preferred_domain = _domain_for_cookie(name)
        domain_match = 1 if preferred_domain in domain else 0
        non_empty_domain = 1 if domain else 0
        return (domain_match, non_empty_domain, len(path), secure)

    def normalize_cookie_records(records):
        kept_by_name = {}
        changes = []
        ordered_passthrough = []

        for record in records:
            name = str(record.get('name') or '')
            if not _is_critical_cookie_name(name):
                ordered_passthrough.append(record)
                continue

            current = kept_by_name.get(name)
            if current is None:
                kept_by_name[name] = record
                continue

            if _cookie_score(record) >= _cookie_score(current):
                changes.append({'name': name, 'dropped': current, 'kept': record})
                kept_by_name[name] = record
            else:
                changes.append({'name': name, 'dropped': record, 'kept': current})

        normalized = ordered_passthrough + list(kept_by_name.values())
        return normalized, changes

    def success_path_label(stage, rebuild_retry=False):
        if stage == 'first_submit':
            return 'First submission entered success path after session rebuild' if rebuild_retry else 'First submission entered success path'
        if stage == 'same_session_retry':
            return 'Retry entered success path after session rebuild' if rebuild_retry else 'Retry within same session entered success path'
        return 'Entered success path'

# ================= Configuration Constants =================
RENEW_DAYS = 7
CACHE_FILE_NAME = 'hiden_cookies.json'
LOCAL_CACHE_PATH = os.path.join(os.path.dirname(__file__), CACHE_FILE_NAME)

# ================= Global Log Collector =================
ALL_LOGS = []

def log_print(msg):
    print(msg)
    ALL_LOGS.append(str(msg))

# ================= WebDAV Module =================
class WebDavManager:
    def __init__(self):
        self.url = os.environ.get("WEBDAV_URL", "")
        self.user = os.environ.get("WEBDAV_USER")
        self.password = os.environ.get("WEBDAV_PASS")

        if self.url and not self.url.endswith('/'):
            self.url += '/'
        self.full_url = self.url + CACHE_FILE_NAME if self.url else ""

    def download(self):
        if not self.url or not self.user:
            log_print("⚠️ WebDAV not configured, skipping cloud sync")
            return

        log_print("☁️ Downloading cache from Infinicloud...")
        try:
            res = requests.get(self.full_url, auth=(self.user, self.password), timeout=30)
            if res.status_code == 200:
                with open(LOCAL_CACHE_PATH, 'w', encoding='utf-8') as f:
                    f.write(res.text)
                log_print("✅ Cloud cache downloaded successfully")
            elif res.status_code == 404:
                log_print("⚪ No cloud cache file yet (first run)")
            else:
                log_print(f"⚠️ Download failed, status code: {res.status_code}")
        except Exception as e:
            log_print(f"❌ WebDAV download error: {e}")

    def upload(self, data):
        if not self.url or not self.user:
            return

        log_print("☁️ Uploading latest cache to Infinicloud...")
        try:
            json_str = json.dumps(data, indent=2)
            res = requests.put(
                self.full_url,
                data=json_str,
                auth=(self.user, self.password),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            if res.status_code in [200, 201, 204]:
                log_print("✅ Cloud cache uploaded successfully")
            else:
                log_print(f"❌ WebDAV upload failed: {res.status_code}")
        except Exception as e:
            log_print(f"❌ WebDAV upload error: {e}")

# ================= Helper Utilities =================
def sleep_random(min_ms=3000, max_ms=8000):
    sec = random.randint(min_ms, max_ms) / 1000.0
    time.sleep(sec)

class CacheManager:
    @staticmethod
    def load():
        if os.path.exists(LOCAL_CACHE_PATH):
            try:
                with open(LOCAL_CACHE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                log_print("Failed to read local cache")
        return {}

    @staticmethod
    def update(index, cookie_str, upload=True):
        """Only write/upload when content actually changes, reducing unnecessary WebDAV requests."""
        data = CacheManager.load()
        key = str(index)

        if data.get(key) == cookie_str:
            return  # No change, skip

        data[key] = cookie_str
        with open(LOCAL_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        log_print(f"💾 [Account {index + 1}] Local cache updated")

        if upload:
            WebDavManager().upload(data)

# ================= Core Bot Class =================
class HidenCloudBot:
    def __init__(self, env_cookie, index):
        self.index = index + 1
        self.base_url = "https://dash.hidencloud.com"
        self.env_cookie = env_cookie
        self.session = self.create_session()

        self.csrf_token = ""
        self.services = []
        # Cross-service dedup set to avoid repeated payment attempts on the same invoice
        self.processed_invoices = set()
        # Invoices confirmed unpayable on current page during this run, avoid re-opening per service
        self.non_payable_invoices = set()
        # Flag whether this account recommends GitHub Actions to re-run later this cycle
        self.retry_needed = False

        cached_data = CacheManager.load()
        cached_cookie = cached_data.get(str(index))

        if cached_cookie:
            log_print(f"[Account {self.index}] Found local cached Cookie, using it first...")
            self.load_cookie_str(cached_cookie)
        else:
            log_print(f"[Account {self.index}] Using environment variable Cookie...")
            self.load_cookie_str(env_cookie)

    def log(self, msg):
        log_print(f"[Account {self.index}] {msg}")

    def mark_retry_needed(self, reason):
        self.retry_needed = True
        if reason:
            self.log(f"🔁 Marked this run for retry: {reason}")

    def create_session(self):
        return cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )

    def load_cookie_str(self, cookie_str):
        if not cookie_str:
            return
        for cookie in parse_seed_cookie_string(cookie_str):
            self.session.cookies.set_cookie(
                requests.cookies.create_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie.get('path', '/'),
                    secure=bool(cookie.get('secure', True)),
                )
            )

    def get_cookie_str(self):
        return '; '.join([f"{c.name}={c.value}" for c in self.session.cookies])

    def normalize_critical_cookies(self, stage=""):
        records = []
        for cookie in self.session.cookies:
            records.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain or '',
                'path': cookie.path or '/',
                'secure': bool(cookie.secure),
                'expires': cookie.expires,
                'rest': getattr(cookie, '_rest', {}) or {},
            })

        normalized, changes = normalize_cookie_records(records)
        if not changes:
            return False

        new_jar = requests.cookies.RequestsCookieJar()
        for record in normalized:
            new_jar.set_cookie(
                requests.cookies.create_cookie(
                    name=record['name'],
                    value=record['value'],
                    domain=record.get('domain', ''),
                    path=record.get('path', '/'),
                    secure=bool(record.get('secure', False)),
                    expires=record.get('expires'),
                    rest=record.get('rest', {}),
                )
            )
        self.session.cookies = new_jar

        changed_names = []
        for change in changes:
            name = change['name']
            if name not in changed_names:
                changed_names.append(name)
        stage_text = f"{stage} " if stage else ""
        self.log(f"[COOKIE_NORMALIZED] {stage_text}Detected and normalized critical Cookie: {', '.join(changed_names)}")
        return True

    def find_cookie_value(self, *names, preferred_domain=''):
        matches = []
        target_names = set(names)

        for cookie in self.session.cookies:
            if cookie.name in target_names and cookie.value:
                matches.append(cookie)

        if not matches:
            return ""

        if preferred_domain:
            domain_matches = [
                cookie for cookie in matches
                if cookie.domain and preferred_domain in cookie.domain
            ]
            if domain_matches:
                matches = domain_matches

        # requests may throw CookieConflictError on same-name cookies; manually pick the best match.
        matches.sort(key=lambda cookie: (len(cookie.domain or ''), len(cookie.path or '')))
        return matches[-1].value

    def save_cookies(self, upload=True):
        """Called explicitly at key operation points, not triggered on every request."""
        CacheManager.update(self.index - 1, self.get_cookie_str(), upload=upload)

    def reset_to_env(self, env_cookie):
        self.session.cookies.clear()
        self.load_cookie_str(env_cookie)
        self.log("Switching back to environment variable Cookie for retry...")

    def rebuild_session(self, cookie_str=None):
        self.session = self.create_session()
        self.csrf_token = ""
        if cookie_str:
            self.load_cookie_str(cookie_str)

    def rebuild_session_and_reinit(self):
        current_cookie = self.get_cookie_str()
        self.log("♻️ Rebuilding session and re-verifying login status...")
        self.rebuild_session(current_cookie)

        if self.init():
            return True, 'invoice_page'

        self.log("⚠️ Current Cookie failed to initialize after session rebuild, falling back to environment variable Cookie for another try...")
        self.rebuild_session()
        self.load_cookie_str(self.env_cookie)
        return self.init()

    def request(self, method, url, data=None, headers=None):
        full_url = urljoin(self.base_url, url)
        try:
            resp = self.session.request(method, full_url, data=data, headers=headers, timeout=30)
            self.normalize_critical_cookies(f"{method} {url}")
            return resp
        except Exception as e:
            self.log(f"Request exception: {e}")
            raise

    def _refresh_csrf(self, soup):
        """Refresh CSRF token from page HTML to prevent 419 errors from expired tokens."""
        token_tag = soup.find('meta', attrs={'name': 'csrf-token'})
        if token_tag:
            self.csrf_token = token_tag['content']
            return
        # Fallback: read from form _token field
        token_input = soup.find('input', attrs={'name': '_token'})
        if token_input:
            self.csrf_token = token_input['value']

    def normalize_url(self, url):
        return urljoin(self.base_url, url)

    def has_invoice_payment_context(self, text):
        normalized = re.sub(r'\s+', ' ', text or '').strip().lower()
        if not normalized:
            return False

        positive_keywords = [
            'unpaid', 'pending', 'pay now', 'payment due', 'pay invoice',
            'pendiente', 'pagar ahora', 'sin pagar',
            '未支付', '待支付', '待付款', '立即支付', '去支付', '付款', '支付'
        ]
        negative_keywords = [
            'paid', 'completed', 'cancelled', 'canceled', 'refunded',
            'pagado', 'completado', 'cancelado', 'reembolsado',
            '已支付', '已付款', '已完成', '已取消', '已退款', '作废'
        ]

        has_positive = any(self.contains_context_keyword(normalized, keyword) for keyword in positive_keywords)
        has_negative = any(self.contains_context_keyword(normalized, keyword) for keyword in negative_keywords)
        return has_positive and not has_negative

    def contains_context_keyword(self, normalized_text, keyword):
        if re.search(r'[a-z0-9]', keyword):
            pattern = rf'(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])'
            return re.search(pattern, normalized_text) is not None
        return keyword in normalized_text

    def extract_invoice_links(self, soup, require_payment_context=False):
        invoice_links = []

        if require_payment_context:
            containers = soup.find_all(['tr', 'li', 'div', 'article', 'section'])
            for container in containers:
                links = []
                for a in container.find_all('a', href=True):
                    href = a['href']
                    if '/invoice/' in href and 'download' not in href:
                        links.append(self.normalize_url(href))

                if not links:
                    continue

                container_text = container.get_text(" ", strip=True)
                if self.has_invoice_payment_context(container_text):
                    invoice_links.extend(links)

            return sorted(set(invoice_links))

        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/invoice/' in href and 'download' not in href:
                invoice_links.append(self.normalize_url(href))
        return sorted(set(invoice_links))

    def extract_server_error_message(self, soup):
        selectors = [
            '[role="alert"]',
            '[class*="alert"]',
            '[class*="text-red"]',
            '[class*="text-danger"]',
            '[class*="bg-red"]',
            '[class*="border-red"]',
            '[class*="error"]',
        ]
        ignored_phrases = [
            'this action is irreversible',
            'permanently deleted',
            'delete server',
            'sign out',
        ]
        error_keywords = [
            'error', 'failed', 'failure', 'must ', 'cannot', 'not allowed',
            'restricted', 'connect your discord', 'only renew',
            '错误', '失败', '无法', '不能', '不允许', '受限'
        ]

        for element in soup.select(','.join(selectors)):
            text = re.sub(r'\s+', ' ', element.get_text(" ", strip=True)).strip()
            if not text:
                continue

            normalized = text.lower()
            if any(phrase in normalized for phrase in ignored_phrases):
                continue
            if any(keyword in normalized for keyword in error_keywords):
                return text

        return ""

    def extract_form_payload(self, form):
        payload = {}

        for field in form.find_all(['input', 'select', 'textarea']):
            name = field.get('name')
            if not name or field.has_attr('disabled'):
                continue

            tag_name = field.name.lower()
            if tag_name == 'input':
                field_type = (field.get('type') or '').lower()
                if field_type in ('checkbox', 'radio') and not field.has_attr('checked'):
                    continue
                payload[name] = field.get('value', '')
            elif tag_name == 'select':
                option = field.find('option', selected=True) or field.find('option')
                payload[name] = option.get('value', '') if option else ''
            else:
                payload[name] = field.get_text()

        return payload

    def find_renew_form(self, soup, service_id):
        exact_path = f"/service/{service_id}/renew"
        fallback_form = None
        fallback_action = ""

        for form in soup.find_all('form'):
            action = form.get('action', '')
            if not action:
                continue

            action_url = self.normalize_url(action)
            if exact_path in action_url:
                return form, action_url

            form_text = form.get_text(" ", strip=True)
            if '/renew' in action_url or 'renew' in form_text.lower() or 'renew' in form_text:
                fallback_form = form
                fallback_action = action_url

        return fallback_form, fallback_action

    def fetch_manage_page(self, service_id):
        manage_res = self.request('GET', f"/service/{service_id}/manage")
        soup = BeautifulSoup(manage_res.text, 'html.parser')
        self._refresh_csrf(soup)
        return manage_res, soup

    def submit_renew_request(self, service_id, soup, referer_url):
        form, action_url = self.find_renew_form(soup, service_id)
        payload = self.extract_form_payload(form) if form else {}

        token_input = soup.find('input', attrs={'name': '_token'})
        if token_input and not payload.get('_token'):
            payload['_token'] = token_input.get('value', '')

        payload['days'] = RENEW_DAYS

        target_url = action_url or self.normalize_url(f"/service/{service_id}/renew")
        xsrf_cookie = self.find_cookie_value(
            'XSRF-TOKEN',
            'XSRF_TOKEN',
            'csrf_token',
            preferred_domain='dash.hidencloud.com'
        )
        headers = {
            'X-CSRF-TOKEN': self.csrf_token,
            'Referer': referer_url,
            'Origin': self.base_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        if xsrf_cookie:
            headers['X-XSRF-TOKEN'] = unquote(xsrf_cookie)
        return self.request('POST', target_url, data=payload, headers=headers)

    def try_handle_invoice_from_response(self, service_id, response, allow_invoice_poll=True):
        if '/invoice/' in response.url:
            self.log("⚡️ Renewal successful, redirected to invoice page, auto-executing payment...")
            pay_result = self.perform_pay_from_html(response.text, response.url)
            if pay_result in {'paid', 'already_processed'}:
                return True, 'invoice_page'
            if not allow_invoice_poll:
                return False, None
            self.log("⚠️ Redirected invoice page is not payable, switching to check current service unpaid invoices...")
            invoice_polled = self.check_and_pay_invoices(service_id, is_precheck=False, retries=6, retry_delay=8)
            if invoice_polled:
                return True, 'invoice_poll'
            return False, None

        soup_resp = BeautifulSoup(response.text, 'html.parser')
        server_error = self.extract_server_error_message(soup_resp)
        if server_error:
            self.log(f"⚠️ Renewal request rejected by server, page message: {server_error}")
            return True, 'server_reject'

        invoice_links = self.extract_invoice_links(soup_resp, require_payment_context=False)
        if invoice_links:
            for invoice_url in invoice_links:
                self.log(f"🔗 Found invoice link in response HTML: {invoice_url}")
                pay_result = self.pay_single_invoice(invoice_url)
                if pay_result in {'paid', 'already_processed'}:
                    return True, 'invoice_link'

            if not allow_invoice_poll:
                return False, None

            self.log("⚠️ Invoice links in response are not payable, switching to check current service unpaid invoices...")
            invoice_polled = self.check_and_pay_invoices(service_id, is_precheck=False, retries=6, retry_delay=8)
            if invoice_polled:
                return True, 'invoice_poll'
            return False, None

        err_div = soup_resp.find('div', class_=re.compile(r'(alert-danger|text-danger|error)'))
        if err_div:
            self.log(f"⚠️ Renewal request rejected by server, page message: {err_div.get_text(strip=True)}")
            return True, 'server_reject'

        if not allow_invoice_poll:
            return False, None

        if response.status_code == 419:
            self.log("⚠️ Renewal request returned 419, no redirect after retry, checking if invoice was generated...")
        else:
            self.log(f"⚠️ Submission succeeded but no auto-redirect, response URL: {response.url} | Status code: {response.status_code}")
            self.log("Post-submission polling for invoices...")

        invoice_polled = self.check_and_pay_invoices(service_id, is_precheck=False, retries=6, retry_delay=8)
        if invoice_polled:
            return True, 'invoice_poll'
        return False, None

    def init(self):
        self.log("Verifying login status...")
        try:
            res = self.request('GET', '/dashboard')

            if '/login' in res.url:
                self.log("❌ Current Cookie has expired")
                return False

            soup = BeautifulSoup(res.text, 'html.parser')
            log_print(f"ð [Debug] Page title: {soup.title.string if soup.title else 'No title'}") #VW

            self._refresh_csrf(soup)

            self.services = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/service/' in href and '/manage' in href:
                    svc_id = href.split('/service/')[1].split('/')[0]
                    if not any(s['id'] == svc_id for s in self.services):
                        self.services.append({'id': svc_id, 'url': href})

            self.log(f"✅ Login successful, found {len(self.services)} services.")
            self.save_cookies(upload=True)
            return True
        except Exception as e:
            self.log(f"❌ Initialization exception: {e}")
            return False

    def process_service(self, service, allow_rebuild_retry=True, skip_initial_delay=False, rebuild_retry=False):
        if not skip_initial_delay:
            sleep_random(2000, 4000)
        self.log(f">>> Processing service ID: {service['id']}")

        try:
            # 1. Precheck: clear legacy unpaid invoices (already processed ones are filtered by processed_invoices)
            self.check_and_pay_invoices(service['id'], is_precheck=True)

            # 2. Fetch manage page and refresh CSRF token
            manage_res, soup = self.fetch_manage_page(service['id'])

            # ================== 3. Check if Renewal is Allowed ==================
            renew_btn = soup.find('button', onclick=re.compile(r'showRenewAlert'))
            if renew_btn:
                onclick_val = renew_btn['onclick']
                match = re.search(r'showRenewAlert\((\d+),\s*(\d+),\s*(true|false)\)', onclick_val)
                if match:
                    days_until = int(match.group(1))
                    threshold = int(match.group(2))
                    is_free = match.group(3) == 'true'

                    if days_until > threshold:
                        threshold_text = "1 day" if threshold == 1 else f"{threshold} days"
                        kind = "Free service" if is_free else "Service"
                        self.log(f"⏳ Not yet time for renewal: {kind} must have less than {threshold_text} remaining to renew. Currently: {days_until} days remaining.")
                        return

            # ================== 4. Execute Single Precise Renewal ==================
            token_input = soup.find('input', attrs={'name': '_token'})
            if not token_input:
                self.log("❌ Cannot find renewal Token (service may have expired or page structure changed)")
                return

            self.log(f"Submitting renewal ({RENEW_DAYS} days)...")
            sleep_random(1000, 2000)

            submit_stage = 'first_submit'
            res = self.submit_renew_request(service['id'], soup, manage_res.url)
            handled, outcome = self.try_handle_invoice_from_response(service['id'], res, allow_invoice_poll=False)

            if not handled and res.status_code == 419:
                self.log("♻️ First renewal request returned 419, refreshing manage page to get new Token and retrying...")
                sleep_random(1000, 2000)
                manage_res, soup = self.fetch_manage_page(service['id'])
                submit_stage = 'same_session_retry'
                res = self.submit_renew_request(service['id'], soup, manage_res.url)
                handled, outcome = False, None

            # ================== 5. Result Validation and Payment ==================
            if not handled:
                handled, outcome = self.try_handle_invoice_from_response(service['id'], res)

            if handled and outcome in {'invoice_page', 'invoice_link', 'invoice_poll'}:
                self.log(f"[RENEW_RESULT] {success_path_label(submit_stage, rebuild_retry=rebuild_retry)}")
            elif handled and outcome == 'server_reject':
                self.log(f"[RENEW_RESULT] {"After session rebuild" if rebuild_retry else "Current session"} submission rejected by server")

            if not handled and allow_rebuild_retry and res.status_code == 419:
                self.log("♻️ Renewal still failed within current session, simulating Job re-run: rebuilding session and fully retrying current service once...")
                if self.rebuild_session_and_reinit():
                    self.process_service(service, allow_rebuild_retry=False, skip_initial_delay=True, rebuild_retry=True)
                else:
                    self.log("❌ Still unable to re-login after session rebuild, abandoning this service for this run")
                    self.mark_retry_needed(f"Service {service['id']} still unable to complete renewal after session rebuild")
            elif not handled:
                self.mark_retry_needed(f"Service {service['id']} renewal not completed this run")

        except Exception as e:
            self.log(f"Processing exception: {e}")
            self.mark_retry_needed(f"Service {service['id']} processing exception")
        finally:
            # Save cookies after each service, not after every request
            self.save_cookies(upload=True)

    def check_and_pay_invoices(self, service_id, is_precheck=False, retries=1, retry_delay=5):
        if not is_precheck:
            sleep_random(2000, 3000)

        for attempt in range(retries):
            try:
                res = self.request('GET', f"/service/{service_id}/invoices?where=unpaid")
                soup = BeautifulSoup(res.text, 'html.parser')
                invoice_links = self.extract_invoice_links(soup, require_payment_context=True)

                # Filter out invoices already processed this run to avoid duplicate operations
                unique_invoices = [url for url in set(invoice_links)
                                   if url not in self.processed_invoices
                                   and url not in self.non_payable_invoices]

                if not unique_invoices:
                    if retries > 1 and attempt < retries - 1:
                        self.log(f"⚪ Check #{attempt+1} found no new invoices, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    if not is_precheck:
                        self.log("⚪ No unpaid invoices")
                    return False

                self.log(f"🔍 Found {len(unique_invoices)} unpaid invoices, preparing to process...")
                paid_any = False
                for url in unique_invoices:
                    pay_result = self.pay_single_invoice(url)
                    if pay_result in {'paid', 'already_processed'}:
                        paid_any = True
                    sleep_random(3000, 5000)
                return paid_any

            except Exception as e:
                self.log(f"Error checking invoices: {e}")
                self.mark_retry_needed(f"Service {service_id} invoice query exception")
                return False

    def pay_single_invoice(self, url):
        normalized_url = self.normalize_url(url)
        if normalized_url in self.processed_invoices:
            self.log(f"⏭️ Invoice already processed, skipping duplicate payment: {normalized_url}")
            return 'already_processed'
        if normalized_url in self.non_payable_invoices:
            self.log(f"⏭️ Invoice not payable, skipping duplicate check: {normalized_url}")
            return 'non_payable'

        try:
            self.log(f"📄 Opening invoice: {normalized_url}")
            res = self.request('GET', normalized_url)
            return self.perform_pay_from_html(res.text, normalized_url)
        except Exception as e:
            self.log(f"Failed to access invoice: {e}")
            self.mark_retry_needed("Invoice page access failed")
            return 'invoice_fetch_failed'

    def perform_pay_from_html(self, html_content, current_url):
        normalized_current_url = self.normalize_url(current_url)
        if normalized_current_url in self.processed_invoices:
            self.log(f"⏭️ Invoice already processed, skipping duplicate payment: {normalized_current_url}")
            return 'already_processed'
        if normalized_current_url in self.non_payable_invoices:
            self.log(f"⏭️ Invoice not payable, skipping duplicate check: {normalized_current_url}")
            return 'non_payable'

        soup = BeautifulSoup(html_content, 'html.parser')
        self._refresh_csrf(soup)

        target_form = None
        target_action = ""

        for form in soup.find_all('form'):
            action = form.get('action', '')
            if not action or 'balance/add' in action:
                continue
            btn = form.find('button')
            # Match both English "pay" and Chinese payment button text
            if btn and ('pay' in btn.get_text().lower() or '支付' in btn.get_text()):
                target_form = form
                target_action = action
                break

        # Fallback: any form whose action contains 'invoice' or 'payment' and has a submit button
        if not target_form:
            for form in soup.find_all('form'):
                action = form.get('action', '')
                if any(kw in action for kw in ['/invoice/', '/payment/']) and 'balance/add' not in action:
                    if form.find('button'):
                        target_form = form
                        target_action = action
                        self.log(f"🔁 Fallback matched payment form: {action}")
                        break

        if not target_form:
            page_title = soup.title.string.strip() if soup.title and soup.title.string else "No title"
            page_text = soup.get_text(" ", strip=True)
            if not self.has_invoice_payment_context(page_text):
                self.non_payable_invoices.add(normalized_current_url)
                self.log(f"⚪ Invoice page does not show unpaid/payment entry, marking as unpayable this run and skipping: {normalized_current_url}")
                return 'non_payable'
            else:
                self.log(f"⚠️ No usable payment form found, page structure may have changed. Title: {page_title}")
                self.mark_retry_needed(f"Invoice {normalized_current_url} page structure appears changed")
                return 'payment_form_missing'

        payload = {}
        for inp in target_form.find_all('input'):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                payload[name] = value

        self.log("👉 Submitting payment...")
        try:
            action_url = self.normalize_url(target_action)
            headers = {'X-CSRF-TOKEN': self.csrf_token, 'Referer': current_url}
            res = self.request('POST', action_url, data=payload, headers=headers)

            if res.status_code == 200:
                self.log("✅ Payment successful!")
                self.processed_invoices.add(normalized_current_url)
                return 'paid'
            else:
                self.log(f"⚠️ Payment response: {res.status_code}")
                self.mark_retry_needed(f"Invoice {normalized_current_url} payment response abnormal")
                return 'payment_failed'
        except Exception as e:
            self.log(f"❌ Payment failed: {e}")
            self.mark_retry_needed(f"Invoice {normalized_current_url} payment exception")
            return 'payment_failed'

# ================= Main Program =================
if __name__ == '__main__':
    env_cookies = os.environ.get("HIDEN_COOKIE", "")
    cookies_list = re.split(r'[&\n]', env_cookies)
    cookies_list = [c for c in cookies_list if c.strip()]
    any_retry_needed = False

    if not cookies_list:
        log_print("❌ Environment variable HIDEN_COOKIE not configured")
        sys.exit(1)

    WebDavManager().download()

    log_print(f"\n=== HidenCloud Renewal Script Started (Python) ===")

    for i, cookie in enumerate(cookies_list):
        bot = HidenCloudBot(cookie, i)
        success = bot.init()

        if not success:
            bot.reset_to_env(cookie)
            success = bot.init()

        if success:
            for service in bot.services:
                bot.process_service(service)
        else:
            log_print(f"Account {i + 1}: Login failed, please check Cookie")
            bot.mark_retry_needed("Account initialization failed")

        if bot.retry_needed:
            any_retry_needed = True

        log_print("\n----------------------------------------\n")
        if i < len(cookies_list) - 1:
            sleep_random(5000, 10000)

    final_content = "\n".join(ALL_LOGS)
    if final_content:
        send_notify("HidenCloud Renewal Report", final_content)

    if any_retry_needed:
        log_print("🔁 Retriable failures found this run, script will exit with code 1 for GitHub Actions to re-run later")
        sys.exit(1)

    sys.exit(0)
