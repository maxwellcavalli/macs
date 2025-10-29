To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, and R2DBC. You can do this by using your favorite IDE or by running the following command in the terminal:
```bash
curl https://start.spring.io/starter.zip -o my-project.zip
unzip my-project.zip
cd my-project
```
1. Create a new package named `repository` inside the main package. Inside this package, create a new class called `UserRepository`. This class will extend the `R2dbcJpaRepository` interface and define methods for querying users.
```java
package com.example.myproject.repository;

import com.example.myproject.model.User;
import org.springframework.data.r2dbc.repository.R2dbcJpaRepository;

public interface UserRepository extends R2dbcJpaRepository<User, Long> {
}
```
1. Create a new package named `service` inside the main package. Inside this package, create a new class called `UserService`. This class will implement methods for querying users using the repository.
```java
package com.example.myproject.service;

import com.example.myproject.model.User;
import com.example.myproject.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class UserService {

    @Autowired
    private UserRepository userRepository;

    public Flux<User> getAllUsers() {
        return userRepository.findAll();
    }
}
```
1. Create a new package named `controller` inside the main package. Inside this package, create a new class called `UserController`. This class will define endpoints for querying users using the service.
```java
package com.example.myproject.controller;

import com.example.myproject.model.User;
import com.example.myproject.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Flux;

@RestController
public class UserController {

    @Autowired
    private UserService userService;

    @GetMapping("/users")
    public Flux<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```
1. Create a new package named `model` inside the main package. Inside this package, create a new class called `User`. This class will define the User entity.
```java
package com.example.myproject.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.r2dbc.core.mapping.Document;

@Document(collection = "users")
public class User {

    @Id
    private Long id;
    private String name;
    private String email;

    // getters and setters
}
```
1. Run the application by running the following command in the terminal:
```bash
./mvnw spring-boot:run
```
Now you have a repository, service, and controller to query users using R2DBC in Spring Boot. You can test the endpoints by sending GET requests to `http://localhost:8080/users`.