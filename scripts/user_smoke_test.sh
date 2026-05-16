#!/usr/bin/env bash
# AutoAgent 用户冒烟测试（无需 LLM API Key）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AUTOAGENT_WORKSPACE="$ROOT"
export AUTOAGENT_MEMORY_PATH="$ROOT/.autoagent-test/memory.db"
export AUTOAGENT_STATE_PATH="$ROOT/.autoagent-test/run_state.json"
export AUTOAGENT_LOG_PATH="$ROOT/.autoagent-test/run.log"
mkdir -p "$ROOT/.autoagent-test"

PY="${ROOT}/.venv/bin/python"
AA="${ROOT}/.venv/bin/autoagent"

if [[ ! -x "$AA" ]]; then
  echo "请先运行: uv sync --extra dev"
  exit 1
fi

echo "==> config"
"$AA" config

echo "==> plan (heuristic)"
"$AA" plan "用户测试：预览计划"

echo "==> run --approve"
"$AA" run "用 echo 回显 USER_SMOKE_OK" --approve

echo "==> history"
"$AA" history --limit 5

echo "==> detach + status"
"$AA" run "后台任务 smoke" --approve --detach
sleep 2
"$AA" status

echo ""
echo "用户冒烟测试完成。LLM 路径请手动执行:"
echo "  $AA run \"你的目标\" --llm --approve"
echo "  $AA status --watch"
