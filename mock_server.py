#!/usr/bin/env python3
"""
Mock Protobuf Server for Charles Proxy
Serves JSON files as encoded protobuf responses dynamically
"""

import os
import sys
import json
import tempfile
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

class ProtobufMockHandler(BaseHTTPRequestHandler):
    """HTTP request handler that encodes JSON to protobuf on-the-fly"""
    
    # Configuration - will be set by main()
    endpoints = {}
    
    def do_GET(self):
        """Handle GET requests"""
        self._handle_request()
    
    def do_POST(self):
        """Handle POST requests"""
        self._handle_request()
    
    def _handle_request(self):
        """Main request handler - encodes JSON to protobuf and returns it"""
        try:
            # Match endpoint from path
            endpoint_path = self.path.split('?')[0]  # Remove query params
            
            if endpoint_path not in self.endpoints:
                available = list(self.endpoints.keys())
                self._send_error(404, f"Endpoint not found: {endpoint_path}\nAvailable: {available}")
                return
            
            # Get configuration for this endpoint
            config = self.endpoints[endpoint_path]
            json_file = config['json_file']
            proto_file = config['proto_file']
            message_type = config['message_type']
            proto_root = config.get('proto_root')  # Optional root for imports
            
            # Log request
            print(f"\n📥 Incoming request: {self.command} {self.path}")
            print(f"   Endpoint: {endpoint_path}")
            print(f"   JSON: {json_file}")
            print(f"   Proto: {proto_file}")
            print(f"   Message: {message_type}")
            if proto_root:
                print(f"   Proto Root: {proto_root}")
            
            # Read and validate JSON
            if not os.path.exists(json_file):
                self._send_error(404, f"JSON file not found: {json_file}")
                return
            
            with open(json_file, 'r') as f:
                json_data = json.load(f)
            
            print(f"   ✓ JSON loaded: {len(json.dumps(json_data))} bytes")
            
            # Encode to protobuf
            proto_data = self._encode_to_protobuf(json_data, proto_file, message_type, proto_root)
            
            if proto_data is None:
                self._send_error(500, "Failed to encode protobuf")
                return
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-protobuf')
            self.send_header('Content-Length', str(len(proto_data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(proto_data)
            
            print(f"   ✓ Response sent: {len(proto_data)} bytes (protobuf)")
            print(f"   📤 Status: 200 OK\n")
            
        except json.JSONDecodeError as e:
            self._send_error(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self._send_error(500, f"Server error: {str(e)}")
    
    def _encode_to_protobuf(self, json_data: dict, proto_file: str, message_type: str, proto_root: Optional[str] = None) -> Optional[bytes]:
        """Encode JSON data to protobuf using protoc"""
        try:
            # Create temporary directory for compilation
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Write JSON to temporary file
                json_temp = temp_path / "input.json"
                with open(json_temp, 'w') as f:
                    json.dump(json_data, f)
                
                # Compile .proto file
                proto_path = Path(proto_file).absolute()
                
                # Use proto_root if provided, otherwise use parent directory
                if proto_root:
                    proto_include_dir = Path(proto_root).absolute()
                else:
                    proto_include_dir = proto_path.parent
                
                # Find all proto files that need to be compiled (dependencies)
                proto_files_to_compile = [proto_path]
                if proto_root:
                    # Parse imports and add them
                    imports = self._find_proto_imports(proto_path, proto_include_dir)
                    proto_files_to_compile.extend(imports)
                
                # Deduplicate proto files
                proto_files_to_compile = list(dict.fromkeys(proto_files_to_compile))
                
                compile_cmd = [
                    'protoc',
                    f'--python_out={temp_dir}',
                    f'-I{proto_include_dir}',
                ] + [str(p) for p in proto_files_to_compile]
                
                result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"   ✗ protoc compilation failed: {result.stderr}")
                    return None
                
                # Import the generated module
                # Calculate the relative path from proto_root to get the module path
                if proto_root:
                    proto_include_dir = Path(proto_root).absolute()
                    relative_proto = proto_path.relative_to(proto_include_dir)
                    # Convert path to module name: proto/external/sc/api.proto -> proto.external.sc.api_pb2
                    module_parts = list(relative_proto.parts[:-1]) + [relative_proto.stem + '_pb2']
                    proto_module_name = '.'.join(module_parts)
                else:
                    proto_module_name = proto_path.stem + '_pb2'
                
                sys.path.insert(0, temp_dir)
                
                try:
                    proto_module = __import__(proto_module_name, fromlist=[''])
                except ImportError as e:
                    print(f"   ✗ Failed to import generated module: {e}")
                    print(f"   Module name tried: {proto_module_name}")
                    return None
                
                # Get the message class
                try:
                    message_class = getattr(proto_module, message_type)
                except AttributeError:
                    available = [name for name in dir(proto_module) if not name.startswith('_')]
                    print(f"   ✗ Message type '{message_type}' not found")
                    print(f"   Available types: {available}")
                    return None
                
                # Create and populate message
                message = message_class()
                self._populate_message(message, json_data)
                
                # Serialize to binary
                proto_bytes = message.SerializeToString()
                
                # Clean up sys.path
                sys.path.remove(temp_dir)
                
                return proto_bytes
                
        except Exception as e:
            print(f"   ✗ Encoding error: {str(e)}")
            return None
    
    def _populate_message(self, message, data):
        """Recursively populate protobuf message from JSON data"""
        from google.protobuf import struct_pb2
        from google.protobuf.descriptor import FieldDescriptor
        
        if not isinstance(data, dict):
            return
        
        for key, value in data.items():
            # Handle field name variations (e.g., header_ -> header)
            actual_key = key
            if not hasattr(message, key):
                # Try without trailing underscore
                if key.endswith('_'):
                    alternate_key = key[:-1]
                    if hasattr(message, alternate_key):
                        actual_key = alternate_key
                    else:
                        continue
                else:
                    continue
            
            # Get field descriptor to check the type
            try:
                field = message.DESCRIPTOR.fields_by_name.get(actual_key)
                if field is None:
                    continue
                    
                # Check if this is a google.protobuf.Struct field
                if field.message_type and field.message_type.full_name == 'google.protobuf.Struct':
                    if isinstance(value, dict):
                        struct_field = getattr(message, actual_key)
                        # Use ParseDict for google.protobuf.Struct
                        from google.protobuf.json_format import ParseDict
                        ParseDict(value, struct_field)
                        continue
                
                # Check if this is a map field with Struct values
                if field.message_type and field.message_type.GetOptions().map_entry:
                    # This is a map field
                    map_field = getattr(message, actual_key)
                    if isinstance(value, dict):
                        for map_key, map_value in value.items():
                            # Check if map value is Struct
                            value_field = field.message_type.fields_by_name.get('value')
                            if value_field and value_field.message_type and value_field.message_type.full_name == 'google.protobuf.Struct':
                                # Map value is Struct, parse specially
                                from google.protobuf.json_format import ParseDict
                                ParseDict(map_value, map_field[map_key])
                            elif isinstance(map_value, dict):
                                # Regular nested message in map
                                nested = map_field[map_key]
                                self._populate_message(nested, map_value)
                            else:
                                # Simple value in map
                                map_field[map_key] = map_value
                        continue
            except Exception as e:
                # If we can't get field info, fall back to old behavior
                pass
            
            if isinstance(value, dict):
                # Nested message
                nested = getattr(message, actual_key)
                self._populate_message(nested, value)
            elif isinstance(value, list):
                # Repeated field
                field = getattr(message, actual_key)
                for item in value:
                    if isinstance(item, dict):
                        nested = field.add()
                        self._populate_message(nested, item)
                    else:
                        field.append(item)
            else:
                # Simple field
                try:
                    setattr(message, actual_key, value)
                except (TypeError, ValueError):
                    # Try to handle type mismatches
                    if isinstance(value, str) and value.isdigit():
                        setattr(message, actual_key, int(value))
                    elif isinstance(value, (int, float)):
                        setattr(message, actual_key, value)
    
    def _find_proto_imports(self, proto_file: Path, proto_root: Path) -> list:
        """Find all proto files imported by this proto file (recursively)"""
        imports = []
        seen = set()
        
        def parse_imports(pfile: Path):
            if pfile in seen:
                return
            seen.add(pfile)
            
            try:
                with open(pfile, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('import '):
                            # Extract import path: import "proto/path/file.proto";
                            import_match = line.split('"')
                            if len(import_match) >= 2:
                                import_path = import_match[1]
                                full_import_path = proto_root / import_path
                                if full_import_path.exists():
                                    imports.append(full_import_path)
                                    # Recursively parse this import
                                    parse_imports(full_import_path)
            except Exception as e:
                print(f"   ⚠️  Warning: Could not parse imports from {pfile}: {e}")
        
        parse_imports(proto_file)
        return imports
    
    def _send_error(self, code: int, message: str):
        """Send error response"""
        print(f"   ✗ Error {code}: {message}\n")
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(message.encode())
    
    def log_message(self, format, *args):
        """Override to suppress default logging"""
        pass


def load_endpoints_config(config_file='endpoints.json'):
    """Load endpoints configuration from JSON file"""
    script_dir = Path(__file__).parent
    config_path = script_dir / config_file
    
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}")
        print(f"💡 Create an 'endpoints.json' file with your endpoint configuration")
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Convert list format to dict format for easier lookup
        endpoints_dict = {}
        for endpoint in config.get('endpoints', []):
            path = endpoint.get('path')
            if not path:
                continue
            
            # Resolve relative paths to absolute
            json_file = endpoint.get('json_file', '')
            if json_file and not os.path.isabs(json_file):
                json_file = str(script_dir / json_file)
            
            endpoints_dict[path] = {
                'json_file': json_file,
                'proto_file': endpoint.get('proto_file', ''),
                'message_type': endpoint.get('message_type', ''),
                'proto_root': endpoint.get('proto_root')
            }
        
        return endpoints_dict
    
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Mock Protobuf Server for Charles Proxy - Multiple Endpoints',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Start server with default config (endpoints.json)
  python3 mock_server.py
  
  # Custom port
  python3 mock_server.py -P 8081
  
  # Custom config file
  python3 mock_server.py -c my_endpoints.json
  
  # Then in Charles Proxy Map Remote:
  #   Map From: https://api.yourapp.com/getProfile
  #   Map To:   http://localhost:8080/getProfile
        '''
    )
    
    parser.add_argument('-P', '--port', type=int, default=8080,
                        help='Port to run server on (default: 8080)')
    parser.add_argument('--host', default='localhost',
                        help='Host to bind to (default: localhost)')
    parser.add_argument('-c', '--config', default='endpoints.json',
                        help='Path to endpoints config file (default: endpoints.json)')
    
    args = parser.parse_args()
    
    # Load endpoints from config file
    ENDPOINTS = load_endpoints_config(args.config)
    
    # Validate all endpoint files exist
    errors = []
    for endpoint, config in ENDPOINTS.items():
        json_file = os.path.abspath(config['json_file'])
        proto_file = os.path.abspath(config['proto_file'])
        
        if not os.path.exists(json_file):
            errors.append(f"  ✗ {endpoint}: JSON file not found: {json_file}")
        if not os.path.exists(proto_file):
            errors.append(f"  ✗ {endpoint}: Proto file not found: {proto_file}")
        
        # Update with absolute paths
        config['json_file'] = json_file
        config['proto_file'] = proto_file
    
    if errors:
        print("❌ Configuration errors:\n")
        for error in errors:
            print(error)
        print("\n💡 Edit the ENDPOINTS dict in the script to configure your endpoints")
        sys.exit(1)
    
    # Set configuration
    ProtobufMockHandler.endpoints = ENDPOINTS
    
    # Start server
    server_address = (args.host, args.port)
    httpd = HTTPServer(server_address, ProtobufMockHandler)
    
    print("=" * 70)
    print("🚀 Mock Protobuf Server Started")
    print("=" * 70)
    print(f"📍 Server:      http://{args.host}:{args.port}")
    print(f"\n📋 Configured Endpoints:")
    for endpoint, config in ENDPOINTS.items():
        print(f"\n  {endpoint}")
        print(f"    JSON:    {os.path.basename(config['json_file'])}")
        print(f"    Proto:   {os.path.basename(config['proto_file'])}")
        print(f"    Message: {config['message_type']}")
    print("\n" + "=" * 70)
    print("\n✅ Ready to serve protobuf responses!")
    print(f"\n💡 In Charles Proxy Map Remote:")
    print(f"   Map From: https://api.yourapp.com/getProfile")
    print(f"   Map To:   http://{args.host}:{args.port}/getProfile")
    print(f"\n⏸️  Press Ctrl+C to stop\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down server...")
        httpd.shutdown()
        print("✅ Server stopped\n")


if __name__ == '__main__':
    main()

