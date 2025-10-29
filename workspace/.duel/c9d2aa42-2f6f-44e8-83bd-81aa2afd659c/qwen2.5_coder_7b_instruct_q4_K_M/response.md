To create a new repository, service, and controller to query the `user` table in your project, you need to follow these steps:

1. **Create a Repository Interface:**
   This interface will handle database operations related to the `user` table.

2. **Implement the Repository:**
   Create a class that implements the repository interface and provides concrete implementations for the database operations.

3. **Create a Service Class:**
   This service class will use the repository to perform business logic related to the `user` table.

4. **Create a Controller Class:**
   This controller class will handle HTTP requests and interact with the service layer to return responses.

Let's assume your project structure is as follows:
```
src/
├── main/
│   ├── java/
│   │   └── com/
│   │       └── example/
│   │           └── demo/
│   │               ├── controller/
│   │               ├── model/
│   │               ├── repository/
│   │               ├── service/
│   │               └── DemoApplication.java
```

### Step 1: Create a Repository Interface

**File:** `src/main/java/com/example/demo/repository/UserRepository.java`
```java
package com.example.demo.repository;

import com.example.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {
    User findByUsername(String username);
}
```

### Step 2: Implement the Repository

**File:** `src/main/java/com/example/demo/repository/UserRepositoryImpl.java`
```java
package com.example.demo.repository;

import com.example.demo.model.User;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepositoryImpl implements UserRepository {
    // You can add custom query methods here if needed
}
```

### Step 3: Create a Service Class

**File:** `src/main/java/com/example/demo/service/UserService.java`
```java
package com.example.demo.service;

import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;

    public User getUserByUsername(String username) {
        return userRepository.findByUsername(username);
    }
}
```

### Step 4: Create a Controller Class

**File:** `src/main/java/com/example/demo/controller/UserController.java`
```java
package com.example.demo.controller;

import com.example.demo.model.User;
import com.example.demo.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {
    @Autowired
    private UserService userService;

    @GetMapping("/user")
    public User getUser(@RequestParam String username) {
        return userService.getUserByUsername(username);
    }
}
```

### Summary

- **Repository Interface (`UserRepository.java`):** Defines methods for database operations.
- **Repository Implementation (`UserRepositoryImpl.java`):** Provides concrete implementations (if needed).
- **Service Class (`UserService.java`):** Handles business logic using the repository.
- **Controller Class (`UserController.java`):** Handles HTTP requests and interacts with the service layer.

This structure follows a clean separation of concerns, making your codebase easier to maintain and scale.