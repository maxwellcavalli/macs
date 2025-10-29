package com.example.demo.repository;

File: src/main/java/com/example/user/repository/UserRepository.java

public interface UserRepository extends JpaRepository<User, Long> {
    Flux<User> findByUsername(String username);
}
