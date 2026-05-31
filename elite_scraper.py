import requests
import re
import base64
import os
import logging
from datetime import datetime, timedelta
import concurrent.futures

# ==========================================
# 🛡 ZERO TRUST: GLOBAL GITHUB HUNTER
# ==========================================
GH_FILE = "secret_feed/github_hunter_links.txt"
TG_FILE = "secret_feed/telegram_links.txt"
WEB_FILE = "secret_feed/web_links.txt"

GH_TOKEN = os.getenv("GH_TOKEN") # Токен для поиска, чтобы избежать лимитов API

# Лимиты Аккумулятора (как ты и просил: 400к потолок)
MAX_POOL_SIZE = 400000
PRUNE_TO_SIZE = 350000

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')

def get_global_blacklist():
    """
    🧮 Кросс-Дедупликация: Собираем все ссылки, которые УЖЕ есть в Телеграме и Вебе.
    """
    blacklist = set()
    for file_path in [TG_FILE, WEB_FILE]:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    links = f.read().splitlines()
                    blacklist.update(links)
                logging.info(f"🛡️ Добавлено в черный список из {file_path}: {len(links)} ссылок")
            except Exception as e:
                logging.warning(f"⚠️ Ошибка чтения {file_path}: {e}")
    return blacklist

def get_dynamic_repos():
    """
    🌐 Широкий радар: Ищет живые репозитории по всему GitHub за последние 7 дней.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GH_TOKEN: headers["Authorization"] = f"token {GH_TOKEN}"
        
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Широкий спектр поисковых запросов
    queries = [
        f"v2ray subscription pushed:>{seven_days_ago}",
        f"vless proxy pushed:>{seven_days_ago}",
        f"free nodes pushed:>{seven_days_ago}",
        f"xray config pushed:>{seven_days_ago}",
        f"clash yaml pushed:>{seven_days_ago}",
        f"vmess reality pushed:>{seven_days_ago}"
    ]
    
    found_repos = set()
    for q in queries:
        try:
            url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page=30"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    found_repos.add(item['full_name'])
        except Exception as e:
            logging.error(f"❌ Ошибка поиска GitHub API: {e}")

    logging.info(f"🔍 Радар нашел {len(found_repos)} свежих репозиториев для ковровой проверки.")
    return list(found_repos)

def extract_all_links(raw_text):
    """🛡️ Параноидальная двойная расшифровка (Plain + Base64)"""
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria|tuic|socks5)://[^\s<"\'\)]+')
    found = set(regex.findall(raw_text))
    try:
        clean_b64 = re.sub(r'\s+', '', raw_text)
        clean_b64 = re.sub(r'[^a-zA-Z0-9+/=]', '', clean_b64)
        pad = len(clean_b64) % 4
        if pad: clean_b64 += '=' * (4 - pad)
        decoded_text = base64.b64decode(clean_b64).decode('utf-8', errors='ignore')
        found.update(regex.findall(decoded_text))
    except Exception:
        pass
    return list(found)

def scan_repo_for_links(repo_name):
    """
    Сканирует не только README, но и типичные файлы подписок в репозитории.
    """
    # Запросы к raw.githubusercontent.com не расходуют лимит API!
    files_to_check = ['README.md', 'sub.txt', 'proxies.txt', 'vless.txt', 'vmess.txt', 'mixed.txt', 'all.txt']
    branches_to_check = ['main', 'master']
    
    found_links = []
    for branch in branches_to_check:
        for file in files_to_check:
            url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/{file}"
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    found_links.extend(extract_all_links(r.text))
            except:
                pass
    return found_links

def main():
    logging.info("🚀 [Global Hunter] Запуск широкого сканирования GitHub...")
    
    # 1. Загружаем черный список (всё, что уже есть в ТГ и Вебе)
    global_blacklist = get_global_blacklist()
    
    # 2. Ищем репозитории
    repos = get_dynamic_repos()
    
    # 3. Сканируем файлы в репозиториях в 30 потоков
    new_found_links = []
    logging.info(f"📦 Запуск коврового парсинга {len(repos)} репозиториев...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        results = executor.map(scan_repo_for_links, repos)
        for res_list in results:
            new_found_links.extend(res_list)

    # 4. Отсеиваем мусор и ГЛОБАЛЬНЫЕ ДУБЛИКАТЫ
    unique_new_links = []
    for link in new_found_links:
        link = link.strip()
        # Если ссылки нет в черном списке и мы её еще не добавили в пул:
        if link not in global_blacklist and link not in unique_new_links:
            unique_new_links.append(link)
            
    logging.info(f"💎 Найдено абсолютно новых уникальных ссылок: {len(unique_new_links)}")

    # 5. Читаем старую базу Хантера
    existing_hunter_links = []
    if os.path.exists(GH_FILE):
        try:
            with open(GH_FILE, "r", encoding="utf-8") as f:
                existing_hunter_links = f.read().splitlines()
        except Exception:
            pass

    # 6. Слияние и Аккумулятор
    unique_new_links.reverse()
    combined = list(dict.fromkeys(existing_hunter_links + unique_new_links))
    logging.info(f"🧮 Итого в пуле Охотника: {len(combined)}")
    
    if len(combined) > MAX_POOL_SIZE:
        logging.info(f"✂️ Превышен лимит {MAX_POOL_SIZE}. Стрижка старых серверов...")
        combined = combined[-PRUNE_TO_SIZE:]
        
    if not combined:
        logging.warning("⚠️ Пул Охотника пуст.")
        return

    # 7. Запись
    os.makedirs(os.path.dirname(GH_FILE), exist_ok=True)
    with open(GH_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(combined))
        
    logging.info(f"✅ База Охотника сохранена: {len(combined)} строк.")

if __name__ == "__main__":
    main()
