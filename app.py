from flask import Flask, render_template, request
import subprocess

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run-script', methods=['POST'])
def run_script():
    singer_name = request.form['singer_name']
    number_of_videos = request.form['number_of_videos']
    duration = request.form['duration']
    final_filename = request.form['final_filename']
    
    # Call the 102203804.py script
    command = ['python3', '102203804.py', singer_name, number_of_videos, duration, final_filename]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode == 0:
        return "Script executed successfully!"
    else:
        return f"Error: {result.stderr}"

if __name__ == '__main__':
    app.run(debug=True)
