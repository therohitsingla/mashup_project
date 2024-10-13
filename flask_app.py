# Requirements:-
# Flask==2.0.1
# yt-dlp==2021.12.17
# moviepy==1.0.3
# pydub==0.25.1

from flask import Flask, request, jsonify, send_file
import os
import sys
import yt_dlp
from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy.editor import VideoFileClip
from pydub import AudioSegment

app = Flask(__name__)

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

@app.route('/create_mashup', methods=['POST'])
@app.route('/')
def home():
    return 'Hello, this is your Flask app!'

def create_mashup_api():
    data = request.json
    singer_name = data['singer_name']
    number_of_videos = int(data['num_videos'])
    duration = int(data['video_duration'])
    email = data['email']
    final_mashup_filename = f"{singer_name}_mashup.mp3"

    if number_of_videos < 10 or number_of_videos > 50:
        return jsonify({"error": "Number of videos must be between 10 and 50"}), 400

    folder_path = os.path.join(os.getcwd(), "1.links")
    file_name = "links.txt"

    links = search_youtube_music_links(f"{singer_name} official new video song", number_of_videos)

    if not links:
        return jsonify({"error": "No links found for the query"}), 404

    try:
        write_links_to_file(links, folder_path, file_name)
        download_audio_from_links(folder_path, file_name)

        audio_folder = os.path.join(os.getcwd(), "3.audios")
        mashup_folder = os.path.join(os.getcwd(), "4.mashup")
        os.makedirs(mashup_folder, exist_ok=True)

        create_mashup(audio_folder, final_mashup_filename, duration)

        return send_file(os.path.join(mashup_folder, final_mashup_filename), as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)