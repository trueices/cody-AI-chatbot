# Use the official Python image as the base image
FROM --platform=linux/amd64  python:3.11

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy the rest of the application files into the container
COPY . .

# Expose the port that Gunicorn will listen on
EXPOSE 5000

# Set environment variables if necessary (optional)
# ENV FLASK_ENV=production

# Command to run the Flask app with Gunicorn
CMD ["gunicorn", "--timeout", "1000", "--bind", "0.0.0.0:5000", "--workers", "2", "application:application"]