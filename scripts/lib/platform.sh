#!/bin/bash
# Cross-platform helpers for Meta-Ralph (macOS, Linux, Git Bash on Windows).

is_windows() {
  case "$(uname -s 2>/dev/null)" in
    MINGW* | MSYS* | CYGWIN* | Windows_NT) return 0 ;;
  esac
  [ "${OS:-}" = "Windows_NT" ] && return 0
  return 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

python_cmd() {
  local candidate

  for candidate in python3 python; do
    if command_exists "$candidate"; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done

  return 1
}

venv_python() {
  local venv_dir="$1"
  if is_windows; then
    echo "${venv_dir}/Scripts/python.exe"
  else
    echo "${venv_dir}/bin/python"
  fi
}

venv_pip() {
  local venv_dir="$1"
  if is_windows; then
    echo "${venv_dir}/Scripts/pip.exe"
  else
    echo "${venv_dir}/bin/pip"
  fi
}

resolve_venv_python() {
  local venv_dir="$1"
  local py
  py="$(venv_python "$venv_dir")"
  if [ -x "$py" ] || [ -f "$py" ]; then
    echo "$py"
    return 0
  fi
  return 1
}

is_process_running() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_dashboard_background() {
  local python_bin="$1"
  local server_py="$2"
  local port="$3"
  local board_file="$4"
  local log_file="$5"

  nohup "$python_bin" "$server_py" --port "$port" --board "$board_file" --no-browser >"$log_file" 2>&1 &
  echo $!
}

run_cursor_agent() {
  local prompt_file="$1"
  local prompt
  prompt="$(cat "$prompt_file")"

  if command_exists cursor-agent; then
    cursor-agent --print --trust --force -- "$prompt"
    return $?
  fi

  if command_exists agent; then
    agent --print --trust --force -- "$prompt"
    return $?
  fi

  return 127
}

git_bash_path() {
  if [ -n "${META_RALPH_GIT_BASH:-}" ] && [ -x "$META_RALPH_GIT_BASH" ]; then
    echo "$META_RALPH_GIT_BASH"
    return 0
  fi

  if command_exists bash; then
    command -v bash
    return 0
  fi

  local candidate
  for candidate in \
    "/c/Program Files/Git/bin/bash.exe" \
    "/c/Program Files (x86)/Git/bin/bash.exe"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}
