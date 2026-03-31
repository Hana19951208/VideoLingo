import streamlit as st
import os, sys, time
from core.st_utils.imports_and_utils import *
from core.st_utils.log_viewer import list_preview_files, load_preview_content
from core.st_utils.task_runner import TaskRunner
from core.st_utils.workflow_registry import (
    build_runner_steps,
    describe_stage_steps,
    get_dependency_steps,
    get_stage,
    get_stage_steps,
    normalize_path,
    normalize_preview_patterns,
)
from core import *
from core.utils.rerun_cleanup import cleanup_stage_outputs, collect_existing_artifacts, step_has_all_artifacts

# SET PATH
current_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + current_dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="VideoLingo", page_icon="docs/logo.svg")

FLASH_MESSAGE_PREFIX = "_workflow_flash_message::"
FLASH_LEVEL_PREFIX = "_workflow_flash_level::"


# ─── Task control UI (auto-refreshes every 1s while task is active) ───


@st.fragment(run_every=1)
def _task_control_panel(runner_key: str):
    """Renders progress bar + pause/stop buttons. Auto-refreshes every 1s."""
    runner = TaskRunner.get(st.session_state, runner_key)

    if runner.state == "idle":
        return

    # Progress
    step_text = (
        f"({runner.current_step + 1}/{runner.total_steps}) {t(runner.current_label)}"
        if runner.current_step >= 0
        else ""
    )

    if runner.is_active:
        if runner.state == "paused":
            st.warning(f"⏸️ {t('Paused')} {step_text}")
        else:
            st.info(f"⏳ {t('Running...')} {step_text}")
        st.progress(runner.progress)

        # Control buttons
        col1, col2 = st.columns(2)
        with col1:
            if runner.state == "paused":
                if st.button(
                    f"▶️ {t('Resume')}",
                    key=f"{runner_key}_resume",
                    use_container_width=True,
                ):
                    runner.resume()
                    st.rerun()
            else:
                if st.button(
                    f"⏸️ {t('Pause')}",
                    key=f"{runner_key}_pause",
                    use_container_width=True,
                ):
                    runner.pause()
                    st.rerun()
        with col2:
            if st.button(
                f"⏹️ {t('Stop')}",
                key=f"{runner_key}_stop",
                use_container_width=True,
                type="primary",
            ):
                runner.stop()
                st.rerun()

    elif runner.state == "completed":
        st.success(t("Task completed!"))
        st.progress(1.0)
        runner.reset()
        time.sleep(0.5)
        st.rerun(scope="app")

    elif runner.state == "stopped":
        st.warning(f"⏹️ {t('Task stopped')} {step_text}")
        if st.button(t("OK"), key=f"{runner_key}_ack_stop", use_container_width=True):
            runner.reset()
            st.rerun(scope="app")

    elif runner.state == "error":
        st.error(f"❌ {t('Task error')}: {runner.error_msg}")
        if st.button(t("OK"), key=f"{runner_key}_ack_error", use_container_width=True):
            runner.reset()
            st.rerun(scope="app")


# ─── Text processing ───


def _get_text_steps():
    """Return the subtitle processing steps as (label, callable) list."""
    return build_runner_steps("text")


def _set_workflow_flash(stage_id: str, message: str, level: str = "info"):
    st.session_state[f"{FLASH_MESSAGE_PREFIX}{stage_id}"] = message
    st.session_state[f"{FLASH_LEVEL_PREFIX}{stage_id}"] = level


def _show_workflow_flash(stage_id: str):
    message = st.session_state.pop(f"{FLASH_MESSAGE_PREFIX}{stage_id}", None)
    level = st.session_state.pop(f"{FLASH_LEVEL_PREFIX}{stage_id}", "info")
    if not message:
        return
    getattr(st, level, st.info)(message)


def _toggle_step_details(stage_id: str, step_id: str):
    state_key = f"show_step_details::{stage_id}::{step_id}"
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def _is_step_complete(step):
    return step_has_all_artifacts(step.artifact_patterns)


def _get_missing_dependencies(stage_id: str, step_id: str):
    missing = []
    for dependency_step in get_dependency_steps(stage_id, step_id):
        if not _is_step_complete(dependency_step):
            missing.append(dependency_step)
    return missing


def _render_preview_files(step):
    preview_files = list_preview_files(normalize_preview_patterns(step))
    if not preview_files:
        st.caption("暂无相关日志或中间产物。")
        return

    for preview_file in preview_files:
        st.markdown(f"`{normalize_path(preview_file)}`")
        preview = load_preview_content(preview_file)
        if preview["kind"] == "dataframe":
            st.dataframe(preview["content"], use_container_width=True, hide_index=True)
        else:
            st.code(preview["content"] or "(empty)", language="text")


def _render_step_actions(stage, step, runner):
    stage_id = stage.stage_id
    missing_dependencies = _get_missing_dependencies(stage_id, step.step_id)
    existing_outputs = collect_existing_artifacts(step.artifact_patterns)
    can_run = not runner.is_active and not missing_dependencies

    if missing_dependencies:
        st.warning(
            "缺少上游产物，当前不能直接运行这一步："
            + "、".join(t(item.title) for item in missing_dependencies)
        )
    elif existing_outputs:
        st.caption("命中已有产物，直接运行本步时可能被跳过：")
        st.caption("\n".join(existing_outputs))
    else:
        st.caption("当前步骤尚未产生产物。")

    action_columns = st.columns([1.1, 1.1, 1.1, 1.2])
    if action_columns[0].button(
        "运行本步",
        key=f"run_only::{stage_id}::{step.step_id}",
        disabled=not can_run,
        use_container_width=True,
    ):
        runner.start(build_runner_steps(stage_id, only_step_id=step.step_id))
        st.rerun()

    if action_columns[1].button(
        "从本步重跑",
        key=f"rerun_from::{stage_id}::{step.step_id}",
        disabled=not can_run,
        use_container_width=True,
    ):
        deleted = cleanup_stage_outputs(stage_id, step.step_id, include_downstream=True)
        if deleted:
            _set_workflow_flash(stage_id, "已清理并准备从当前步骤重跑：\n" + "\n".join(deleted), "info")
        runner.start(build_runner_steps(stage_id, start_step_id=step.step_id))
        st.rerun()

    if action_columns[2].button(
        "清理本步及下游",
        key=f"cleanup::{stage_id}::{step.step_id}",
        disabled=runner.is_active,
        use_container_width=True,
    ):
        deleted = cleanup_stage_outputs(stage_id, step.step_id, include_downstream=True)
        if deleted:
            _set_workflow_flash(stage_id, "已清理以下产物：\n" + "\n".join(deleted), "success")
        else:
            _set_workflow_flash(stage_id, "当前没有匹配到可清理的产物。", "info")
        st.rerun()

    if action_columns[3].button(
        "查看日志",
        key=f"toggle_logs::{stage_id}::{step.step_id}",
        use_container_width=True,
    ):
        _toggle_step_details(stage_id, step.step_id)
        st.rerun()

    if st.session_state.get(f"show_step_details::{stage_id}::{step.step_id}", False):
        with st.container(border=True):
            _render_preview_files(step)


def _render_stage_video(stage):
    if not os.path.exists(stage.video_path):
        return

    if load_key("burn_subtitles"):
        st.video(stage.video_path)

    if stage.stage_id == "text":
        download_subtitle_zip_button(text=t("Download All Srt Files"))


def _render_stage_step_list(stage):
    for index, step in enumerate(get_stage_steps(stage.stage_id), start=1):
        completed = _is_step_complete(step)
        status_text = "已完成" if completed else "未完成"
        with st.container(border=True):
            step_header_columns = st.columns([3, 1])
            step_header_columns[0].markdown(f"**{index}. {t(step.title)}**")
            step_header_columns[1].caption(status_text)
            _render_step_actions(stage, step, TaskRunner.get(st.session_state, stage.runner_key))


def _render_stage_controls(stage):
    runner = TaskRunner.get(st.session_state, stage.runner_key)
    if runner.is_active or runner.is_done:
        _task_control_panel(stage.runner_key)

    control_columns = st.columns([1.4, 1.4, 1.1])
    if control_columns[0].button(
        t(stage.start_button_label),
        key=f"run_stage::{stage.stage_id}",
        disabled=runner.is_active,
        use_container_width=True,
    ):
        runner.start(build_runner_steps(stage.stage_id))
        st.rerun()

    if control_columns[1].button(
        "从头重跑本阶段",
        key=f"rerun_stage::{stage.stage_id}",
        disabled=runner.is_active,
        use_container_width=True,
    ):
        first_step = get_stage_steps(stage.stage_id)[0]
        deleted = cleanup_stage_outputs(stage.stage_id, first_step.step_id, include_downstream=True)
        if deleted:
            _set_workflow_flash(stage.stage_id, "已清理当前阶段产物，准备从头重跑。", "info")
        runner.start(build_runner_steps(stage.stage_id))
        st.rerun()

    if control_columns[2].button(
        t("Archive to 'history'"),
        key=f"archive_stage::{stage.stage_id}",
        disabled=runner.is_active,
        use_container_width=True,
    ):
        cleanup()
        st.rerun()


def _render_stage_section(stage_id: str):
    stage = get_stage(stage_id)
    st.header(t(stage.title))

    with st.container(border=True):
        steps_text = "<br>".join(
            f"{index}. {t(step_text)}" for index, step_text in enumerate(describe_stage_steps(stage_id), start=1)
        )
        st.markdown(
            f"""
        <p style='font-size: 20px;'>
        {t("This stage includes the following steps:")}
        <p style='font-size: 20px;'>
            {steps_text}
        """,
            unsafe_allow_html=True,
        )
        _show_workflow_flash(stage_id)
        _render_stage_controls(stage)
        _render_stage_video(stage)
        _render_stage_step_list(stage)


def text_processing_section():
    _render_stage_section("text")


# ─── Audio processing ───


def _get_audio_steps():
    """Return the audio/dubbing processing steps as (label, callable) list."""
    return build_runner_steps("audio")


def audio_processing_section():
    _render_stage_section("audio")


def render_runtime_config_summary():
    config_items = [
        ("Whisper Runtime", "whisper.runtime"),
        ("Detected Language", "whisper.detected_language"),
        ("Target Language", "target_language"),
        ("Demucs", "demucs"),
        ("Burn Subtitles", "burn_subtitles"),
        ("TTS Method", "tts_method"),
    ]
    with st.sidebar.expander("当前关键配置摘要", expanded=False):
        for label, key in config_items:
            try:
                value = load_key(key)
            except Exception as error:
                value = f"读取失败: {error}"
            st.text(f"{label}: {value}")


# ─── Main ───


def main():
    logo_col, _ = st.columns([1, 1])
    with logo_col:
        st.image("docs/logo.png", width="stretch")
    st.markdown(button_style, unsafe_allow_html=True)
    welcome_text = t(
        'Hello, welcome to VideoLingo. If you encounter any issues, feel free to get instant answers with our Free QA Agent <a href="https://share.fastgpt.in/chat/share?shareId=066w11n3r9aq6879r4z0v9rh" target="_blank">here</a>! You can also try out our SaaS website at <a href="https://videolingo.io" target="_blank">videolingo.io</a> for free!'
    )
    st.markdown(
        f"<p style='font-size: 20px; color: #808080;'>{welcome_text}</p>",
        unsafe_allow_html=True,
    )
    # add settings
    with st.sidebar:
        page_setting()
        render_runtime_config_summary()
        st.markdown(give_star_button, unsafe_allow_html=True)
    download_video_section()
    text_processing_section()
    audio_processing_section()


if __name__ == "__main__":
    main()
