# Open UUID Project

A community-driven tool for documenting and managing Bluetooth Low Energy (BLE) UUIDs. This project aims to create an open, searchable database of BLE attributes to help developers and engineers working with Bluetooth devices.

## Features

- Document and manage BLE services, characteristics, and descriptors
- Parse BLE device logs to automatically extract UUID information
- Search and filter attributes by vendor, model, or UUID
- Dark/light theme support
- Sample data for common BLE devices from major manufacturers
- Community-driven database of BLE attributes

## Live Demo

Visit [https://bensmith83.github.io/open-uuid-project](https://bensmith83.github.io/open-uuid-project)

## Local Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/bensmith83/open-uuid-project.git
   cd open-uuid-project
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the backend server:
   ```bash
   cd backend
   uvicorn test:app --reload
   ```

5. Open `frontend/index.html` in your browser

## Backend Deployment

The backend is deployed using Docker and GitHub Actions to a cloud provider. The deployment process is automated through our CI/CD pipeline.

### Manual Deployment

If you want to deploy the backend manually:

1. Build the Docker image:
   ```bash
   docker build -t open-uuid-backend .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 open-uuid-backend
   ```

## Contributing

We welcome contributions! Here's how you can help:

- Add new device UUIDs and their documentation
- Improve the codebase
- Report bugs
- Suggest features
- Submit pull requests

Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting changes.

## License

[MIT](LICENSE)

## Project Goals

1. Create a comprehensive, open database of BLE UUIDs
2. Help developers identify and document BLE attributes
3. Provide a platform for sharing knowledge about BLE devices
4. Improve the development experience for BLE applications

## Acknowledgments

Created by Ben Smith ([@bensmith83](https://github.com/bensmith83))

