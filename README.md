# 🚀 Mock Protobuf Server

A development tool that serves JSON files as encoded protobuf responses. Perfect for testing mobile apps and APIs with Charles Proxy.

## ✨ Features

- 🔄 Serves JSON data as protobuf-encoded responses
- ⚡ Dynamic encoding on-the-fly (no pre-compilation needed)
- 🎯 Multiple endpoint support
- 🔧 Works seamlessly with Charles Proxy
- ✏️ Easy to modify responses (just edit JSON files)
- 📦 Supports complex proto structures with imports

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 2. Configure Endpoints
Edit `endpoints.json` with your endpoint configurations:
```json
{
  "endpoints": [
    {
      "path": "/trending-feed",
      "json_file": "trending.json",
      "proto_file": "/path/to/your/proto/file.proto",
      "message_type": "FeedFetchResponse",
      "proto_root": "/path/to/proto/root"
    }
  ]
}
```

### 3. Start Server
```bash
python3 mock_server.py
```

Server will start at `http://localhost:8080`

### 4. Configure Charles Proxy
Map your production API endpoints to the local mock server:
- **From:** `https://api.yourapp.com/trending-feed`
- **To:** `http://localhost:8080/trending-feed`

## 📖 Full Documentation

For detailed setup instructions, troubleshooting, and advanced usage, see the complete documentation:

👉 **[Mock Protobuf Server Documentation](https://www.notion.so/sharechat/Mock-Protobuf-Server-Documentation-295c4ef6b06d80b3a99ed75bb151cdf3)**

## 📋 Prerequisites

- Python 3.7+
- protoc (Protocol Buffer Compiler)
- Charles Proxy (for API interception)

## 🛠️ Command Line Options

```bash
python3 mock_server.py --help
```

| Option | Default | Description |
|--------|---------|-------------|
| `-P, --port` | 8080 | Port to run server on |
| `--host` | localhost | Host to bind to |
| `-c, --config` | endpoints.json | Path to config file |

## 💡 Example Usage

```bash
# Start with default settings
python3 mock_server.py

# Custom port
python3 mock_server.py -P 8081

# Custom config file
python3 mock_server.py -c my_endpoints.json
```

## 🤝 Contributing

Feel free to open issues or submit pull requests!

## 📝 License

MIT License

