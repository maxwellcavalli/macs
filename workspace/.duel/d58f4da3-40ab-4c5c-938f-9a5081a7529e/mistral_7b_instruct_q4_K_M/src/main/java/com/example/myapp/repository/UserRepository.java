package com.example.myapp.repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserRepository {
    Flux<String> getAllUsers();
    Mono<String> getUserById(String id);
    Mono<String> createUser(String name, String email);
    Mono<String> updateUser(String id, String name, String email);
    Mono<String> deleteUser(String id);
}
