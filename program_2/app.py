import os
import io
import yt_dlp
from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to search YouTube Music links
def search_youtube_music_links(query, max_results, extra_links=10):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'force_generic_extractor': True,
    }

    total_results = max_results + extra_links  # Fetch more links than needed
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_url = f"ytsearch{total_results}:{query}"
        result = ydl.extract_info(search_url, download=False)

    links = []
    for entry in result['entries']:
        try:
            link = f"https://www.youtube.com/watch?v={entry['id']}"
            links.append(link)
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"Skipping {entry['title']}: {e}")

    return links

def download_single_video(url, index, download_path, max_duration=600, min_duration=60):
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best',
        'outtmpl': os.path.join(download_path, f'video_{index}.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'match_filter': lambda info: 'This video is either too long or too short' 
                        if info.get('duration', 0) > max_duration or info.get('duration', 0) < min_duration else None
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Check video duration
            duration = info.get('duration', 0)
            if duration > max_duration:
                logging.info(f"Skipping {url}: Video longer than {max_duration} seconds")
                return None
            elif duration < min_duration:
                logging.info(f"Skipping {url}: Video shorter than {min_duration} seconds")
                return None

            # Download the video if duration is valid
            filename = ydl.prepare_filename(info)
            ydl.download([url])
        
        if os.path.exists(filename):
            logging.info(f"Successfully downloaded: {filename}")
            return filename
        else:
            logging.error(f"File not found after download: {filename}")
            return None
    except yt_dlp.utils.DownloadError as e:
        if "This video is either too long or too short" in str(e):
            logging.info(f"Skipped {url}: Video duration does not meet criteria")
        else:
            logging.error(f"Error downloading video {url}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error downloading video {url}: {str(e)}")
        return None

def download_all_videos(video_urls, download_path, number_of_videos, max_duration=600):
    downloaded_files = []
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(download_single_video, url, index, download_path, max_duration): index
            for index, url in enumerate(video_urls, start=1)
        }

        for future in as_completed(futures):
            try:
                video_file = future.result()
                if video_file:
                    downloaded_files.append(video_file)

                    # Stop downloading when we've reached the required number of videos
                    if len(downloaded_files) == number_of_videos:
                        break
            except Exception as e:
                logging.error(f"Error occurred: {e}")

    # Check if we got the desired number of videos
    if len(downloaded_files) < number_of_videos:
        logging.error(f"Only {len(downloaded_files)} videos downloaded out of {number_of_videos} requested.")
    
    return downloaded_files

def convert_all_videos_to_audio(video_files, audio_folder):
    os.makedirs(audio_folder, exist_ok=True)

    for index, video_file in enumerate(video_files, start=1):
        try:
            video = VideoFileClip(video_file)
            audio_file = os.path.join(audio_folder, f'song_{index}.mp3')
            video.audio.write_audiofile(audio_file, codec='mp3', bitrate='192k', ffmpeg_params=["-loglevel", "quiet"])
            video.close()
            logging.info(f"Converted {video_file} to {audio_file}")
        except Exception as e:
            logging.error(f"Error converting {video_file} to audio: {e}")

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
            logging.info(f'Added {filename} to the mashup')
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    mashup.export(output_file, format='mp3')
    logging.info(f'Mashup saved as {output_file}')

def create_zip(file_path, zip_name):
    app.logger.info(f"Creating zip for file: {file_path}")
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(file_path, os.path.basename(file_path))

    zip_buffer.seek(0)
    
    app.logger.info(f"Zip file created: {zip_name}, size: {len(zip_buffer.getvalue())} bytes")
    return zip_buffer.getvalue()

def send_email(email, zip_data, file_name):
    app.logger.info(f"Sending email to: {email}")
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')

    if not sender_email or not sender_password:
        app.logger.error("Sender email or password not set in environment variables.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Subject'] = f"Your mashup: {file_name}"

    body = "Please find attached your requested mashup file."
    msg.attach(MIMEText(body, 'plain'))

    if zip_data is None or len(zip_data) == 0:
        app.logger.error("No zip data to attach to email.")
        return False

    try:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(zip_data)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={file_name}.zip",
        )
        msg.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        app.logger.info("Email sent successfully")
        return True
    except Exception as e:
        app.logger.error(f"Error sending email: {e}")
        return False

def create_mashup_process(singer_name, number_of_videos, duration, email, max_video_duration=600):
    try:
        links = search_youtube_music_links(f"{singer_name} official new video song", number_of_videos)
        
        if not links:
            return False, "No links found for the query."

        video_folder = '/tmp/videos'
        audio_folder = '/tmp/audios'
        os.makedirs(video_folder, exist_ok=True)
        os.makedirs(audio_folder, exist_ok=True)

        downloaded_videos = download_all_videos(links, video_folder, number_of_videos, max_video_duration)
        
        if not downloaded_videos:
            return False, "No videos were downloaded."

        convert_all_videos_to_audio(downloaded_videos, audio_folder)

        output_filename = f"{singer_name.replace(' ', '_')}_mashup.mp3"
        output_path = os.path.join('/tmp', output_filename)
        
        create_mashup(audio_folder, output_path, duration)

        # Create zip file
        zip_data = create_zip(output_path, output_filename)

        # Send email with zip attachment
        if send_email(email, zip_data, output_filename):
            app.logger.info(f"Mashup sent to {email}: {output_filename}")
        else:
            app.logger.error(f"Failed to send mashup to {email}")

        # Clean up
        for folder in [video_folder, audio_folder]:
            for file in os.listdir(folder):
                os.remove(os.path.join(folder, file))
        os.remove(output_path)

        return True, f"Mashup created and sent to {email}"
    except Exception as e:
        app.logger.error(f"Error in mashup process: {e}")
        return False, str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/create_mashup', methods=['POST'])
def create_mashup_endpoint():
    try:
        singer_name = request.form.get('singer-name', '')
        number_of_videos = request.form.get('num-videos', '')
        duration = request.form.get('video-duration', '')
        email = request.form.get('email', '')
        
        logging.info(f"Received request: singer_name={singer_name}, number_of_videos={number_of_videos}, duration={duration}, email={email}")
        
        if not all([singer_name, number_of_videos, duration, email]):
            return jsonify({'status': 'error', 'message': 'All fields are required'})
        
        try:
            number_of_videos = int(number_of_videos)
            duration = int(duration)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Number of videos and duration must be integers'})
        
        if not (10 <= number_of_videos <= 50):
            return jsonify({'status': 'error', 'message': 'Number of videos must be between 10 and 50'})
        
        if not (1 <= duration <= 500):
            return jsonify({'status': 'error', 'message': 'Duration must be between 1 and 500 seconds'})
        
        success, message = create_mashup_process(singer_name, number_of_videos, duration, email)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Mashup creation process completed. You will receive an email with the mashup soon.'
            })
        else:
            return jsonify({'status': 'error', 'message': message})
    except Exception as e:
        logging.error(f"Unexpected error in create_mashup_endpoint: {e}")
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'})

if __name__ == "__main__":
    # For local development
    app.run(debug=True)
else:
    # For Vercel deployment
    app.debug = False
