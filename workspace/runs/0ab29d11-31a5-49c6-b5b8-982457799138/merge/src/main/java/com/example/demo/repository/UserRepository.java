package com.example.demo.repository;

public interface UserRepository extends R2DBCRepository<UserEntity, Long> {

    Flux<UserEntity> findAllByOrderByCreatedAtDesc();

    Mono<UserEntity> findByEmail(String email);
}
