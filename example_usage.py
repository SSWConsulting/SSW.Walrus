import requests
import time
import sys

API_BASE_URL = "http://localhost:8000/api"


def upload_csv(file_path: str, survey_topic: str = None):
    print(f"Uploading CSV: {file_path}")
    
    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {}
        if survey_topic:
            data['survey_topic'] = survey_topic
        
        response = requests.post(f"{API_BASE_URL}/process-csv", files=files, data=data)
        response.raise_for_status()
        
        result = response.json()
        print(f"✓ Upload successful! Job ID: {result['job_id']}")
        return result['job_id']


def check_status(job_id: str):
    response = requests.get(f"{API_BASE_URL}/status/{job_id}")
    response.raise_for_status()
    return response.json()


def wait_for_completion(job_id: str):
    print("\nWaiting for processing to complete...")
    
    while True:
        status = check_status(job_id)
        print(f"  Status: {status['status']} | Progress: {status['progress']:.1f}% | {status['message']}")
        
        if status['status'] == 'completed':
            print("\n✓ Processing completed successfully!")
            return True
        elif status['status'] == 'failed':
            print("\n✗ Processing failed!")
            return False
        
        time.sleep(2)


def download_report(job_id: str, output_path: str = None):
    if output_path is None:
        output_path = f"survey_report_{job_id}.md"
    
    print(f"\nDownloading report to: {output_path}")
    
    response = requests.get(f"{API_BASE_URL}/download/{job_id}")
    response.raise_for_status()
    
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    print(f"✓ Report downloaded successfully!")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python example_usage.py <csv_file_path> [survey_topic]")
        print("Example: python example_usage.py survey.csv 'Customer Satisfaction'")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    survey_topic = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        job_id = upload_csv(csv_file, survey_topic)
        
        if wait_for_completion(job_id):
            report_path = download_report(job_id)
            print(f"\n🎉 All done! Check your report at: {report_path}")
        else:
            print("\n❌ Processing failed. Check the logs for details.")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to API. Make sure the server is running!")
        print("   Start the server with: python run.py")
    except FileNotFoundError:
        print(f"\n❌ Error: File not found: {csv_file}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()

