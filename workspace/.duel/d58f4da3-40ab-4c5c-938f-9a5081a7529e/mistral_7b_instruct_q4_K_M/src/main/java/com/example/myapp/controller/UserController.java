package com.example.myapp.controller;

import com.example.myapp.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.netty.http.client.reactive.ReactorNettyHttpClient;
import reactor.netty.http.server.reactive.ReactorNettyHttpServer;

@RestController
@RequestMapping("/users")
public class UserController {
    private final UserService userService;

    @Autowired
    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public Flux<String> getAllUsers() {
        return userService.getAllUsers();
    }

    @GetMapping("/{id}")
    public Mono<String> getUserById(@PathVariable String id) {
        return userService.getUserById(id);
    }

    @PostMapping
    public Mono<String> createUser(@RequestBody String name, @RequestBody String email) {
        return userService.createUser(name, email);
    }

    @PutMapping("/{id}")
    public Mono<String> updateUser(@PathVariable String id, @RequestBody String name, @RequestBody String email) {
        return userService.updateUser(id, name, email);
    }

    @DeleteMapping("/{id}")
    public Mono<String> deleteUser(@PathVariable String id) {
        return userService.deleteUser(id);
    }
}
