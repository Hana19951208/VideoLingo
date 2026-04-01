import os
import ast
import pandas as pd
import subprocess
from pydub import AudioSegment
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from core.utils import *
from core.utils.models import *
console = Console()

DUB_VOCAL_FILE = 'output/dub.mp3'

DUB_SUB_FILE = 'output/dub.srt'
DUB_SRC_SUB_FILE = 'output/dub_src.srt'
OUTPUT_FILE_TEMPLATE = f"{_AUDIO_SEGS_DIR}/{{}}.wav"


def _parse_serialized_list(value):
    if not isinstance(value, str):
        return value
    normalized = value.replace("np.float64(", "").replace(")", "")
    return ast.literal_eval(normalized)

def load_and_flatten_data(excel_file):
    """Load and flatten Excel data"""
    df = pd.read_excel(excel_file)
    lines = [_parse_serialized_list(line) for line in df['lines'].tolist()]
    lines = [item for sublist in lines for item in sublist]

    src_lines = []
    if 'src_lines' in df.columns:
        parsed_src_lines = [_parse_serialized_list(line) for line in df['src_lines'].tolist()]
        src_lines = [item for sublist in parsed_src_lines for item in sublist]
    
    new_sub_times = [_parse_serialized_list(time) for time in df['new_sub_times'].tolist()]
    new_sub_times = [item for sublist in new_sub_times for item in sublist]
    
    return df, lines, src_lines, new_sub_times

def get_audio_files(df):
    """Generate a list of audio file paths"""
    audios = []
    for index, row in df.iterrows():
        number = row['number']
        line_count = len(_parse_serialized_list(row['lines']))
        for line_index in range(line_count):
            temp_file = OUTPUT_FILE_TEMPLATE.format(f"{number}_{line_index}")
            audios.append(temp_file)
    return audios

def process_audio_segment(audio_file):
    """Process a single audio segment with MP3 compression"""
    temp_file = f"{audio_file}_temp.mp3"
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', audio_file,
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '64k',
        temp_file
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    audio_segment = AudioSegment.from_mp3(temp_file)
    os.remove(temp_file)
    return audio_segment

def merge_audio_segments(audios, new_sub_times, sample_rate):
    merged_audio = AudioSegment.silent(duration=0, frame_rate=sample_rate)
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn()) as progress:
        merge_task = progress.add_task("🎵 Merging audio segments...", total=len(audios))
        
        for i, (audio_file, time_range) in enumerate(zip(audios, new_sub_times)):
            if not os.path.exists(audio_file):
                console.print(f"[bold yellow]⚠️  Warning: File {audio_file} does not exist, skipping...[/bold yellow]")
                progress.advance(merge_task)
                continue
                
            audio_segment = process_audio_segment(audio_file)
            start_time, end_time = time_range
            
            # Add silence segment
            if i > 0:
                prev_end = new_sub_times[i-1][1]
                silence_duration = start_time - prev_end
                if silence_duration > 0:
                    silence = AudioSegment.silent(duration=int(silence_duration * 1000), frame_rate=sample_rate)
                    merged_audio += silence
            elif start_time > 0:
                silence = AudioSegment.silent(duration=int(start_time * 1000), frame_rate=sample_rate)
                merged_audio += silence
                
            merged_audio += audio_segment
            progress.advance(merge_task)
    
    return merged_audio

def _format_srt_timestamp(timestamp):
    return (
        f"{int(timestamp//3600):02d}:"
        f"{int((timestamp%3600)//60):02d}:"
        f"{int(timestamp%60):02d},"
        f"{int((timestamp*1000)%1000):03d}"
    )


def _write_srt_file(output_path, subtitle_lines, new_sub_times):
    with open(output_path, 'w', encoding='utf-8') as file:
        for index, ((start_time, end_time), line) in enumerate(zip(new_sub_times, subtitle_lines), 1):
            file.write(f"{index}\n")
            file.write(f"{_format_srt_timestamp(start_time)} --> {_format_srt_timestamp(end_time)}\n")
            file.write(f"{line}\n\n")


def create_srt_subtitle_files():
    _, lines, src_lines, new_sub_times = load_and_flatten_data(_8_1_AUDIO_TASK)

    _write_srt_file(DUB_SUB_FILE, lines, new_sub_times)
    rprint(f"[bold green]Subtitle file created: {DUB_SUB_FILE}[/bold green]")

    if src_lines and len(src_lines) == len(new_sub_times):
        _write_srt_file(DUB_SRC_SUB_FILE, src_lines, new_sub_times)
        rprint(f"[bold green]Subtitle file created: {DUB_SRC_SUB_FILE}[/bold green]")
    elif os.path.exists(DUB_SRC_SUB_FILE):
        os.remove(DUB_SRC_SUB_FILE)

def merge_full_audio():
    """Main function: Process the complete audio merging process"""
    console.print("\n[bold cyan]🎬 Starting audio merging process...[/bold cyan]")
    
    with console.status("[bold cyan]📊 Loading data from Excel...[/bold cyan]"):
        df, lines, src_lines, new_sub_times = load_and_flatten_data(_8_1_AUDIO_TASK)
    console.print("[bold green]✅ Data loaded successfully[/bold green]")
    
    with console.status("[bold cyan]🔍 Getting audio file list...[/bold cyan]"):
        audios = get_audio_files(df)
    console.print(f"[bold green]✅ Found {len(audios)} audio segments[/bold green]")
    
    with console.status("[bold cyan]📝 Generating subtitle file...[/bold cyan]"):
        create_srt_subtitle_files()
    
    if not os.path.exists(audios[0]):
        console.print(f"[bold red]❌ Error: First audio file {audios[0]} does not exist![/bold red]")
        return
    
    sample_rate = 16000
    console.print(f"[bold green]✅ Sample rate: {sample_rate}Hz[/bold green]")

    console.print("[bold cyan]🔄 Starting audio merge process...[/bold cyan]")
    merged_audio = merge_audio_segments(audios, new_sub_times, sample_rate)
    
    with console.status("[bold cyan]💾 Exporting final audio file...[/bold cyan]"):
        merged_audio = merged_audio.set_frame_rate(16000).set_channels(1)
        merged_audio.export(DUB_VOCAL_FILE, format="mp3", parameters=["-b:a", "64k"])
    console.print(f"[bold green]✅ Audio file successfully merged![/bold green]")
    console.print(f"[bold green]📁 Output file: {DUB_VOCAL_FILE}[/bold green]")

if __name__ == "__main__":
    merge_full_audio()
