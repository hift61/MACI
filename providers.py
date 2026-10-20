"""LLM API 공급자 선택: OpenRouter(기본), OpenAI, Google Gemini. 셋 다 OpenAI 호환 chat/completions를 씀.

    python benchmark.py --provider gemini --model gemini-3.1-flash ...
    python benchmark.py --provider openai --model gpt-6-luna ...

- 키: 공급자별 파일(프로젝트 폴더 기준, git에 올리지 않음) -> 없으면 환경변수
    openrouter  key.txt          OPENROUTER_API_KEY
    openai      openai_key.txt   OPENAI_API_KEY
    gemini      gemini_key.txt   GEMINI_API_KEY 또는 GOOGLE_API_KEY
- 모델 이름: OpenRouter 형식("openai/...", "google/...")으로 줘도 해당 공급자에서는 앞부분을 떼고 보냄
- --base-url을 직접 주면 그 주소를 씀 (로컬 llama-server 등. 로컬 주소는 키가 필요 없음)
- 추론 강도(--agent-reasoning): OpenRouter는 extra_body.reasoning, OpenAI/Gemini는 reasoning_effort로 보냄
"""
import os
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))

PROVIDERS = {
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_file": "key.txt",
                   "env": ("OPENROUTER_API_KEY",), "prefix": None,
                   "embed_model": "openai/text-embedding-3-small"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_file": "openai_key.txt",
               "env": ("OPENAI_API_KEY",), "prefix": "openai/", "embed_model": "text-embedding-3-small"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_file": "gemini_key.txt",
               "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "prefix": "google/", "embed_model": "gemini-embedding-001"},
}


def add_arguments(parser, embed: bool = False) -> None:
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="openrouter",
                        help="LLM API provider (default openrouter). Each uses its own key file, see providers.py")
    parser.add_argument("--base-url", default=None, help="override the provider's API address (e.g. a local server)")
    parser.add_argument("--api-key-file", default=None,
                        help="override the provider's key file (relative paths use the project directory)")
    if embed:
        parser.add_argument("--embed-model", default=None, help="embedding model (default: the provider's)")


def is_local(base_url: str) -> bool:
    return urlparse(base_url).hostname in ("127.0.0.1", "localhost", "::1")


def base_url(args) -> str:
    return args.base_url or PROVIDERS[args.provider]["base_url"]


def read_key(args) -> str:
    """키 파일 -> 환경변수 순서. 로컬 주소면 'local'"""
    url = base_url(args)
    if is_local(url):
        return "local"
    spec = PROVIDERS[args.provider]
    filename = os.path.join(HERE, args.api_key_file or spec["key_file"])
    if os.path.isfile(filename):
        with open(filename, encoding="utf-8-sig") as file:
            value = file.read().strip()
        if value:
            return value
    for name in spec["env"]:
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    raise SystemExit(f"Missing {args.provider} API key: put it in {filename} or set {' / '.join(spec['env'])}.")


def model_name(args, model: str) -> str:
    """OpenRouter 형식 이름을 공급자 이름으로 ('openai/gpt-x' -> 'gpt-x'). 직접 주소를 쓰면 그대로"""
    prefix = PROVIDERS[args.provider]["prefix"]
    if args.base_url is None and prefix and model.startswith(prefix):
        return model[len(prefix):]
    return model


def embed_model(args) -> str:
    return getattr(args, "embed_model", None) or PROVIDERS[args.provider]["embed_model"]


def reasoning_params(args, effort: str, openrouter_params) -> dict:
    """에이전트 추론 켜기. OpenRouter는 기존 방식(extra_body.reasoning + tool_choice auto), 나머지는 reasoning_effort"""
    if args.provider == "openrouter" or args.base_url:
        return openrouter_params(effort)
    return {"reasoning_effort": effort}
