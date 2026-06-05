import os
import subprocess
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.panel import Panel

from google import genai
from google.genai import types

# ==========================================
# 1. 환경 변수 및 API 키 로드
# ==========================================
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    print("❌ API 키 오류: .env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=api_key)
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 스캔 시 무시할 폴더 (토큰 낭비 방지)
IGNORE_DIRS = {'.git', 'venv', 'env', '__pycache__', '.idea', 'node_modules'}

# ==========================================
# 2. 에이전트 핵심 도구 (하위 폴더 & Git 완벽 지원)
# ==========================================
def scan_project_workspace() -> str:
    """루트 폴더 및 모든 하위 폴더의 파일 목록을 재귀적으로 스캔하여 반환합니다."""
    file_list = []
    try:
        for root, dirs, files in os.walk(BASE_DIR):
            # 무시할 디렉토리 필터링
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                # 절대 경로에서 BASE_DIR 부분을 잘라내어 깔끔한 상대 경로만 유지 (예: dags/extract.py)
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, BASE_DIR)
                file_list.append(rel_path)
                
        if not file_list:
            return "프로젝트 폴더가 비어있습니다."
        
        return f"프로젝트 내 전체 파일 목록:\n" + "\n".join(f"- {f}" for f in file_list)
    except Exception as e:
        return f"파일 목록 스캔 중 에러 발생: {e}"

def read_local_file(filepath: str) -> str:
    """하위 폴더를 포함한 특정 경로의 파일 내용을 읽어옵니다. (예: 'dags/extract_hero.py')"""
    full_path = os.path.join(BASE_DIR, filepath)
    if os.path.exists(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"파일 읽기 에러 ({filepath}): {e}"
    else:
        return f"'{filepath}' 파일을 찾을 수 없습니다. 경로가 정확한지 확인하세요."

def write_local_file(filepath: str, content: str) -> str:
    """지정된 경로에 파일을 생성하거나 덮어씁니다. 하위 폴더가 없으면 자동으로 생성합니다."""
    full_path = os.path.join(BASE_DIR, filepath)
    try:
        # 파일이 들어갈 하위 폴더가 존재하지 않으면 미리 생성
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"성공: '{filepath}' 파일이 성공적으로 작성/수정되었습니다."
    except Exception as e:
        return f"파일 쓰기 에러 ({filepath}): {e}"

def execute_git_command(command: str) -> str:
    """
    로컬 GitHub 저장소에서 Git 명령어를 실행하고 결과를 반환합니다. 
    예: 'git status', 'git diff', 'git log -3'
    """
    if not command.startswith("git "):
        return "보안 경고: 'git'으로 시작하는 명령어만 실행할 수 있습니다."
    
    try:
        # BASE_DIR을 기준으로 터미널 명령어 실행
        result = subprocess.run(
            command, cwd=BASE_DIR, shell=True, 
            capture_output=True, text=True, check=False
        )
        output = result.stdout if result.returncode == 0 else result.stderr
        return f"명령어 '{command}' 실행 결과:\n{output.strip()}"
    except Exception as e:
        return f"Git 명령어 실행 에러: {e}"

# ==========================================
# 3. 최상위 하이엔드 모델 및 채팅 세팅
# ==========================================
TARGET_MODEL = 'gemini-3.5-flash'

agent_instruction = (
    "당신은 사용자의 로컬 환경에 상주하는 시니어 데이터 엔지니어이자 최고 수준의 Python 개발자입니다.\n"
    "당신은 주어진 도구(tools)를 사용하여 파일 시스템 전체를 재귀적으로 탐색하고, 파일을 읽고/쓰며, Git 명령어를 실행할 수 있습니다.\n"
    "1. 프로젝트 구조 파악: `scan_project_workspace`를 사용해 하위 폴더 구조를 파악하세요.\n"
    "2. 코드 수정: `read_local_file`로 코드를 분석하고, `write_local_file`로 하위 폴더의 파일까지 직접 수정하세요.\n"
    "3. GitHub 연동: 코드를 수정한 후 `execute_git_command` 도구를 사용해 'git status', 'git diff' 등으로 변경점을 확인하고 작업을 검증하세요.\n"
    "4. 불필요한 설명은 줄이고, 핵심 분석과 행동(Action) 위주로 전문가답게 답변하세요."
)

config = types.GenerateContentConfig(
    system_instruction=agent_instruction,
    # ⭐️ 4개의 강력한 도구를 모두 에이전트에게 쥐어줍니다.
    tools=[scan_project_workspace, read_local_file, write_local_file, execute_git_command],
    temperature=0.2 
)

try:
    chat_session = client.chats.create(
        model=TARGET_MODEL,
        config=config
    )
except Exception as e:
    console.print(f"[bold red]❌ 세션 생성 실패:[/bold red] {e}")
    exit(1)

# ==========================================
# 4. CLI 터미널 실행 인터페이스
# ==========================================
def main():
    welcome_msg = (
        f"[bold blue]🚀 풀스택 로컬 코딩 에이전트 가동 (Model: {TARGET_MODEL})[/bold blue]\n"
        f"📁 워크스페이스: [yellow]{BASE_DIR}[/yellow]\n"
        f"💡 [green]추천 명령어:[/green]\n"
        f"   - '프로젝트 전체 하위 폴더까지 싹 다 스캔해줘'\n"
        f"   - 'infra_airflow/dags/scripts/ 폴더 안에 있는 파일 분석해 줘'\n"
        f"   - 'git status 확인하고 변경된 파일 내용 요약해 줘'\n"
        f"나가려면 '종료' 또는 'exit' 입력"
    )
    console.print(Panel(welcome_msg, expand=False, border_style="blue"))
    
    while True:
        user_input = Prompt.ask("\n[bold cyan]🧑‍💻 나[/bold cyan]")
        
        if user_input.strip().lower() in ['종료', 'exit', 'quit', 'q']:
            console.print("[bold yellow]에이전트를 종료합니다. 즐거운 코딩 되세요![/bold yellow]")
            break
            
        if not user_input.strip():
            continue

        with console.status(f"[bold magenta]{TARGET_MODEL}가 작업 공간을 스캔하고 추론하는 중...[/bold magenta]", spinner="point"):
            try:
                response = chat_session.send_message(user_input)
                console.print(f"\n[bold blue]🤖 {TARGET_MODEL} Agent:[/bold blue]")
                
                if response.text:
                    console.print(Markdown(response.text))
                else:
                    console.print("[italic]도구를 사용하여 작업을 완료했습니다.[/italic]")
                    
            except Exception as e:
                console.print(f"\n[bold red]❌ 실행 에러:[/bold red] {e}")

if __name__ == "__main__":
    main()