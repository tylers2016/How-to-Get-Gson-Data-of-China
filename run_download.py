import time
import requests
import glob
import re
import logging
from pathlib import Path
from urllib.parse import quote

# --- 全局配置 ---
BASE_URL_GETGSONDB = "https://map.ruiduobao.com/getGsonDB"
BASE_URL_GETCUNADDRESS = "https://map.ruiduobao.com/getCunAddress"
BASE_URL_DOWNLOADVECTOR = "https://map.ruiduobao.com/downloadVector/"
SITE_HOME_URL = "https://map.ruiduobao.com/"
OUTPUT_DIR = Path("2023")
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': SITE_HOME_URL,
    'X-Requested-With': 'XMLHttpRequest'
}

def setup_logging():
    if logging.getLogger().hasHandlers():
        logging.getLogger().handlers.clear()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler('error.log', mode='w', encoding='utf-8')
    file_handler.setLevel(logging.WARNING)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

def download_final_file(session: requests.Session, url: str, save_path: Path):
    """(下载流程的第二步) 下载最终的文件。"""
    try:
        logging.info(f"    - (第2步) 正在下载最终文件: {url}")
        response = session.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 200:
            if len(response.content) < 100:
                 logging.warning(f"下载内容可能无效 (大小: {len(response.content)} B)，已跳过保存: {save_path}")
            else:
                save_path.write_bytes(response.content)
                logging.info(f"    ✔✔✔ 下载成功: {save_path}")
        else:
            logging.error(f"最终下载失败: 服务器返回状态码 {response.status_code}，URL: {url}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"最终下载网络错误: {e}，URL: {url}")

def process_markdown_file(session: requests.Session, md_file_path: Path):
    logging.info(f"===== 开始处理文件: {md_file_path.name} =====")
    
    path_parts = []
    full_name_parts = []
    line_pattern = re.compile(r'\[(.*?)\]\((.*?)\)')

    with open(md_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_strip = line.strip()
            if not line_strip: continue
            match = line_pattern.search(line_strip)
            if not match: continue
            name, code = match.groups()
            level = 0
            if line.startswith('    - '): level = 5
            elif line.startswith('  - '): level = 4
            elif line.startswith('- '): level = 3
            elif line.startswith('## '): level = 2
            elif line.startswith('# '): level = 1
            if level == 0: continue
            path_parts = path_parts[:level - 1]
            full_name_parts = full_name_parts[:level - 1]
            path_parts.append(name)
            full_name_parts.append(name)
            logging.info(f"\n处理 {level} 级: {' / '.join(path_parts)}")

            pre_request_url = ""
            
            if 1 <= level <= 4:
                pre_request_url = f"{BASE_URL_GETGSONDB}?code={code}"
            elif level == 5:
                full_name = "".join(full_name_parts)
                encoded_full_name = quote(full_name)
                pre_request_url = f"{BASE_URL_GETCUNADDRESS}?address={encoded_full_name}"

            if not pre_request_url: continue

            try:
                logging.info(f"    - (第1步) 正在进行预请求: {pre_request_url}")
                pre_response = session.get(pre_request_url, headers=HEADERS, timeout=15)
                
                if pre_response.status_code == 200:
                    data = pre_response.json()
                    if data.get('status') == 'success' and 'filepath' in data:
                        filepath = data['filepath']
                        logging.info(f"    - (第1步) 成功获取filepath: {filepath}")

                        download_param = Path(filepath).stem
                        final_url = f"{BASE_URL_DOWNLOADVECTOR}{quote(download_param)}?format=gson"
                        
                        parent_dir = OUTPUT_DIR.joinpath(*path_parts[:-1])
                        
                        # --- 关键修改：应用新的文件名格式 ---
                        if 1 <= level <= 4:
                            # 格式为: 代码_中文地名.json
                            save_path = parent_dir / f"{code}_{name}.json"
                        elif level == 5:
                            # 第5级保持不变: 完整中文路径.json
                            place_name = "".join(full_name_parts)
                            save_path = parent_dir / f"{place_name}.json"
                        
                        # 确保文件夹存在
                        folder_to_create = parent_dir / name if level != 5 else parent_dir
                        folder_to_create.mkdir(parents=True, exist_ok=True)
                        
                        download_final_file(session, final_url, save_path)
                    else:
                        logging.error(f"预请求响应内容错误: {data.get('message', '无消息')}, URL: {pre_request_url}")
                else:
                    logging.error(f"预请求失败: 服务器返回状态码 {pre_response.status_code}, URL: {pre_request_url}")
            except Exception as e:
                logging.error(f"处理预请求时发生未知错误: {e}, URL: {pre_request_url}")

            time.sleep(1)

# --- 主程序入口 ---
if __name__ == "__main__":
    setup_logging()
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    logging.info(f"输出目录 '{OUTPUT_DIR}' 已准备就绪。")

    md_files = glob.glob("*.md")

    if not md_files:
        logging.warning("在当前目录下未找到任何 .md 文件。")
    else:
        logging.info(f"找到了 {len(md_files)} 个Markdown文件: {', '.join(md_files)}")
        
        for md_file in md_files:
            logging.info(f"\n{'='*20} 为新文件'{md_file}'创建全新会话 {'='*20}")
            session = requests.Session()
            try:
                session.get(SITE_HOME_URL, headers=HEADERS, timeout=10)
                logging.info("新会话初始化成功。")
                process_markdown_file(session, Path(md_file))
            except requests.exceptions.RequestException as e:
                logging.error(f"会话初始化或文件处理失败: {e}")
            finally:
                session.close()
                logging.info(f"文件 '{md_file}' 处理完毕，会话已关闭。")
        
        logging.info("\n===== 所有任务已完成！ =====")