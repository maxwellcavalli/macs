To create a new repository, service, and controller to query the user table, you can follow these steps:

1. Create a new directory for your project in your preferred version control system (e.g., Git).
2. Initialize a new Go module by running `go mod init <module-name>` in the root of your project directory.
3. Create a new service file with the appropriate package organization and import statements to handle user queries. For example:
```go
package main

import (
	"database/sql"
	"fmt"
)

type UserService struct {
	db *sql.DB
}

func NewUserService(db *sql.DB) *UserService {
	return &UserService{db: db}
}

// Implement methods for querying the user table here
```
1. Create a new controller file with the appropriate package organization and import statements to handle HTTP requests related to user queries. For example:
```go
package main

import (
	"net/http"
	"strconv"

	"github.com/gorilla/mux"
)

type UserController struct {
	userService *UserService
}

func NewUserController(userService *UserService) *UserController {
	return &UserController{userService: userService}
}

// Implement methods for handling HTTP requests here
```
1. Create a new repository file with the appropriate package organization and import statements to handle database operations related to user queries. For example:
```go
package main

import (
	"database/sql"
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

// Implement methods for querying the user table here
```
1. Add the necessary import statements to your main.go file to use the new files you've created. For example:
```go
package main

import (
	"github.com/gorilla/mux"
)

func main() {
	// Initialize your database connection and create a new userService, userController, and userRepository
	// Implement the necessary methods for handling HTTP requests and querying the user table
}
```
Please provide the contents of the attached file so that I can help you further.