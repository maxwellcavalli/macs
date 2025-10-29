package com.example.myapp.service;

import com.example.myapp.repository.UserRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public Flux<String> getAllUsers() {
        return userRepository.getAllUsers();
    }

    public Mono<String> getUserById(String id) {
        return userRepository.getUserById(id);
    }

    public Mono<String> createUser(String name, String email) {
        return userRepository.createUser(name, email);
    }

    public Mono<String> updateUser(String id, String name, String email) {
        return userRepository.updateUser(id, name, email);
    }

    public Mono<String> deleteUser(String id) {
        return userRepository.deleteUser(id);
    }
}
