// Repository
// src/main/java/com/example/myproject/repository/UserDatabaseService.java

package com.example.demo.service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserDatabaseService {
    Flux<User> getAllUsers();
    Mono<User> getUserById(Long id);
}
