def delete_dubbing_files():
    from core.utils.rerun_cleanup import cleanup_stage_outputs

    deleted = cleanup_stage_outputs(
        stage_id="audio",
        step_id="c4_generate_audio_segments",
        include_downstream=True,
    )
    if deleted:
        for file_path in deleted:
            print(f"Deleted: {file_path}")
    else:
        print("No dubbing artifacts found to delete.")

if __name__ == "__main__":
    delete_dubbing_files()
