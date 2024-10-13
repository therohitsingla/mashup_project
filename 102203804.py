# Please install following python librarires before executing the file
# ytdlp, moviepy, pydub and ffmpeg (application)

# exectute the python file using command line (terminal) using the following format:-
# python 102203804.py "<singer_name>" <Number_of_videos> <Audio_Duration> <Output_FileName.mp3>
# eg-> python 102203804.py "sharry maan" 12 35 final_mashup.mp3

import os
import sys
import yt_dlp
from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy.editor import VideoFileClip
from pydub import AudioSegment

# Function to search YouTube Music links
def search_youtube_music_links(query, max_results):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'force_generic_extractor': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_url = f"ytsearch{max_results}:{query}"
        result = ydl.extract_info(search_url, download=False)

    links = []
    for entry in result['entries']:
        try:
            link = f"https://www.youtube.com/watch?v={entry['id']}"
            links.append(link)
        except yt_dlp.utils.DownloadError as e:
            print(f"Skipping {entry['title']}: {e}")

    return links

# Function to write links to a text file in a specified folder
def write_links_to_file(links, folder_path, file_name):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    file_path = os.path.join(folder_path, file_name)

    if os.path.exists(file_path):
        os.remove(file_path)

    with open(file_path, 'w') as file:
        for link in links:
            file.write(f"{link}\n")

    if os.stat(file_path).st_size == 0:
        raise ValueError("No links were generated, file is empty!")

def download_single_video(url, index, download_path):
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best',
        'outtmpl': f'{download_path}/video_{index}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        downloaded_files = [f for f in os.listdir(download_path) if f.startswith(f"video_{index}.")]
        if downloaded_files:
            return os.path.join(download_path, downloaded_files[0])
        else:
            print(f"Downloaded video file not found for {url}")
            return None
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None

def download_all_videos(video_urls, download_path):
    downloaded_files = []
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(download_single_video, url, index, download_path): index
            for index, url in enumerate(video_urls, start=1)
        }

        for future in as_completed(futures):
            try:
                video_file = future.result()
                if video_file:
                    downloaded_files.append(video_file)
            except Exception as e:
                print(f"Error occurred: {e}")

    return downloaded_files

def convert_all_videos_to_audio(video_files, audio_folder):
    # Clear previous audio files
    if os.path.exists(audio_folder):
        for f in os.listdir(audio_folder):
            os.remove(os.path.join(audio_folder, f))
    else:
        os.makedirs(audio_folder)

    for index, video_file in enumerate(video_files, start=1):
        try:
            video = VideoFileClip(video_file)
            audio_file = os.path.join(audio_folder, f'song_{index}.mp3')
            video.audio.write_audiofile(audio_file, codec='mp3', bitrate='192k', ffmpeg_params=["-loglevel", "quiet"])
            video.close()
            print(f"Converted {video_file} to {audio_file}")
        except Exception as e:
            print(f"Error converting {video_file} to audio: {e}")

def download_audio_from_links(links_folder, file_name):
    file_path = os.path.join(links_folder, file_name)
    if not os.path.exists(file_path):
        print("Error: Links file does not exist.")
        return

    with open(file_path, 'r') as file:
        links = file.readlines()

    video_folder = os.path.join(os.getcwd(), "2.videos")
    os.makedirs(video_folder, exist_ok=True)

    for f in os.listdir(video_folder):
        os.remove(os.path.join(video_folder, f))
    
    downloaded_videos = download_all_videos([link.strip() for link in links if link.strip()], video_folder)

    if downloaded_videos:
        print(f"Downloaded {len(downloaded_videos)} video files to {video_folder}.")
        
        audio_folder = os.path.join(os.getcwd(), "3.audios")
        convert_all_videos_to_audio(downloaded_videos, audio_folder)

    else:
        print("No video files were downloaded.")

def create_mashup(input_dir, output_file, duration):
    mashup = AudioSegment.silent(duration=0)
    
    for filename in os.listdir(input_dir):
        if filename.endswith('.mp3') or filename.endswith('.wav') or filename.endswith('.ogg'):
            audio_path = os.path.join(input_dir, filename)
            audio = AudioSegment.from_file(audio_path)
            
            if len(audio) > duration * 1000:  # Convert seconds to milliseconds
                audio = audio[:duration * 1000]
            else:
                audio += AudioSegment.silent(duration=(duration * 1000) - len(audio))
            
            mashup += audio
            print(f'Added {filename} to the mashup')
    
    mashup_path = os.path.join(os.getcwd(), "4.mashup", output_file)
    if os.path.exists(mashup_path):
        os.remove(mashup_path)  # Delete the existing mashup file if it exists
    mashup.export(mashup_path, format='mp3')
    print(f'Mashup saved as {mashup_path}')

# Main function
def main():
    if len(sys.argv) < 5:
        print("Input Error; Format:-\nUsage: python codename.py <singer_name> <number_of_videos> <duration_in_seconds> <final_mashup_filename>")
        return

    singer_name = sys.argv[1]
    try:
        number_of_videos = int(sys.argv[2])
        duration = int(sys.argv[3])
    except ValueError:
        print("Error: The number of videos and duration must be integers.")
        return

    final_mashup_filename = sys.argv[4]

    if number_of_videos < 10:
        print("Error: The number of results must be greater than 10.")
        return
    if number_of_videos > 50:
        print("Error: The number of results cannot exceed 50.")
        return

    folder_path = os.path.join(os.getcwd(), "1.links")
    file_name = "links.txt"

    links = search_youtube_music_links(f"{singer_name} official new video song", number_of_videos)

    if not links:
        print("Error: No links found for the query.")
        return

    try:
        write_links_to_file(links, folder_path, file_name)
        print(f"Links saved to {os.path.join(folder_path, file_name)}")

        download_audio_from_links(folder_path, file_name)

        audio_folder = os.path.join(os.getcwd(), "3.audios")
        mashup_folder = os.path.join(os.getcwd(), "4.mashup")
        os.makedirs(mashup_folder, exist_ok=True)

        create_mashup(audio_folder, final_mashup_filename, duration)

    except ValueError as e:
        print(e)

if __name__ == "__main__":
    main()
