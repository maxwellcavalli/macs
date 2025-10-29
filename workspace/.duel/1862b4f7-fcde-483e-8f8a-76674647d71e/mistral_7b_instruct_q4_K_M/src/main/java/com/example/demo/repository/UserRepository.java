File: src/main/java/com/example/myproject/repository

package com.example.myproject.repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserRepository {
    Flux<User> getAllUsers();
    Mono<User> getUserById(Long id);
    // Add other methods as needed
}
