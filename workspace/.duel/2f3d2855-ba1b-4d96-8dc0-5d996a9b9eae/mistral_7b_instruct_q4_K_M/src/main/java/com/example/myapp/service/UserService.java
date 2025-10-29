package com.example.myapp.service;

import com.example.myapp.repository.UserRepository;
import com.example.myapp.model.User;
import reactor.core.publisher.Flux;

public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public Flux<User> getAllUsers() {
        return userRepository.findAll();
    }
}
