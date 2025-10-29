File: project\_root/new-repository.md
```markdown
# New Repository

This is a new repository for a service and endpoint that will allow users to search for other users.
```

File: project\_root/service.py
```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/users', methods=['GET'])
def search_users():
    # Implement user search logic here
    pass

if __name__ == '__main__':
    app.run(debug=True)
```

File: project\_root/endpoint.py
```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/users', methods=['GET'])
def search_users():
    # Implement user search logic here
    pass

if __name__ == '__main__':
    app.run(debug=True)
```