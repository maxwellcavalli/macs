Sure! Let's set up a basic Spring Boot application with R2DBC for querying users. We'll create a repository, a service, and a controller.

### Step 1: Create the Repository

**File:** `src/main/java/com/example/demo/repository/UserRepository.java`

```java
package com.example.demo.repository;

import com.example.demo.model.User;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface UserRepository extends ReactiveCrudRepository<User, Long> {

    @Query("SELECT * FROM users WHERE age > :age")
    Flux<User> findByAgeGreaterThan(int age);
}
```

### Step 2: Create the Service

**File:** `src/main/java/com/example/demo/service/UserService.java`

```java
package com.example.demo.service;

import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class UserService {

    @Autowired
    private UserRepository userRepository;

    public Flux<User> getUsersByAgeGreaterThan(int age) {
        return userRepository.findByAgeGreaterThan(age);
    }
}
```

### Step 3: Create the Controller

**File:** `src/main/java/com/example/demo/controller/UserController.java`

```java
package com.example.demo.controller;

import com.example.demo.model.User;
import com.example.demo.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class UserController {

    @Autowired
    private UserService userService;

    @GetMapping("/users")
    public Flux<User> getUsersByAge(@RequestParam int age) {
        return userService.getUsersByAgeGreaterThan(age);
    }
}
```

### Step 4: Create the User Model

**File:** `src/main/java/com/example/demo/model/User.java`

```java
package com.example.demo.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("users")
public class User {

    @Id
    private Long id;
    private String name;
    private int age;

    // Getters and Setters

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
```

### Step 5: Configure R2DBC in `application.properties`

**File:** `src/main/resources/application.properties`

```properties
spring.r2dbc.url=r2dbc:h2:mem:testdb
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.r2dbc.properties.cache.prepStmtCacheSize=250
```

### Step 6: Create the Database Schema

**File:** `src/main/resources/schema.sql`

```sql
CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    age INT NOT NULL
);
```

### Step 7: Insert Sample Data (Optional)

**File:** `src/main/resources/data.sql`

```sql
INSERT INTO users (name, age) VALUES ('Alice', 30);
INSERT INTO users (name, age) VALUES ('Bob', 25);
INSERT INTO users (name, age) VALUES ('Charlie', 35);
```

This setup provides a basic Spring Boot application with R2DBC for querying users based on their age. You can extend this by adding more complex queries and handling exceptions as needed.