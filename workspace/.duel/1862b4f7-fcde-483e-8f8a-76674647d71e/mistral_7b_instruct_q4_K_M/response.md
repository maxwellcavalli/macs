To create a new implementation to query a user database table using R2DBC for reactive Java, we will follow these steps:

1. Create a repository: We will create a new package named "repository" and inside it, create a new class called "UserRepository". This class will contain methods that will be used to interact with the database.
```java
File: src/main/java/com/example/myproject/repository

package com.example.myproject.repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserRepository {
    Flux<User> getAllUsers();
    Mono<User> getUserById(Long id);
    // Add other methods as needed
}
```
1. Create a service: We will create a new package named "service" and inside it, create a new class called "UserService". This class will contain methods that will use the repository to interact with the database and return the results in a format that can be consumed by the controller.
```java
File: src/main/java/com/example/myproject/service

package com.example.myproject.service;

import com.example.myproject.repository.UserRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public Flux<User> getAllUsers() {
        return userRepository.getAllUsers();
    }

    public Mono<User> getUserById(Long id) {
        return userRepository.getUserById(id);
    }

    // Add other methods as needed
}
```
1. Create a controller: We will create a new package named "controller" and inside it, create a new class called "UserController". This class will contain methods that will receive requests from the client and call the appropriate service methods to retrieve data from the database.
```java
File: src/main/java/com/example/myproject/controller

package com.example.myproject.controller;

import com.example.myproject.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserService userService;

    @Autowired
    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public Flux<User> getAllUsers() {
        return userService.getAllUsers();
    }

    @GetMapping("/{id}")
    public Mono<User> getUserById(@PathVariable Long id) {
        return userService.getUserById(id);
    }

    // Add other methods as needed
}
```
That's it! With these steps, we have created a new implementation to query a user database table using R2DBC for reactive Java.