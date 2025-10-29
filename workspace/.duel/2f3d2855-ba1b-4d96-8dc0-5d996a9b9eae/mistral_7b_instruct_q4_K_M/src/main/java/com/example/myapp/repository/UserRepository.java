package com.example.myapp.repository;

import com.example.myapp.model.User;
import reactor.core.publisher.Flux;

public interface UserRepository extends ReactiveCrudRepository<User, Long> {
}
