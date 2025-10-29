To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, and R2DBC. You can do this by using your favorite IDE or by running the following command in your terminal:
```bash
./mvnw archetype:generate -DgroupId=com.example.myproject -DartifactId=myproject -DarchetypeArtifactId=maven-archetype-quickstart -DinteractiveMode=false
```
1. Create a new package named `repository` inside your project's main package. Inside this package, create a new interface called `UserRepository`. This interface will extend the `R2dbcRepository` interface and define methods for querying users.
```java
package com.example.myproject.repository;

import org.springframework.data.r2dbc.repository.R2dbcRepository;
import reactor.core.publisher.Flux;

public interface UserRepository extends R2dbcRepository<User, String> {
    Flux<User> findAll();
}
```
1. Create a new package named `service` inside your project's main package. Inside this package, create a new class called `UserService`. This class will implement the `UserService` interface and use the `UserRepository` to query users.
```java
package com.example.myproject.service;

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
1. Create a new package named `controller` inside your project's main package. Inside this package, create a new class called `UserController`. This class will implement the `UserController` interface and use the `UserService` to query users.
```java
package com.example.myproject.controller;

import com.example.myproject.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
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
1. Run your Spring Boot application by running the following command in your terminal:
```bash
./mvnw spring-boot:run
```
Now you have a repository, service, and controller set up to query users using R2DBC in Spring Boot. You can customize this code as needed for your specific use case.