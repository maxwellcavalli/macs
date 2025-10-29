package com.example.myapp.config;

import com.example.myapp.repository.UserRepository;
import com.example.myapp.service.UserService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.client.ReactorNettyHttpClient;
import reactor.netty.http.client.server.ServerHttpClient;
import reactor.netty.http.client.server.ServerHttpClientBuilder;

@Configuration
public class AppConfig {
    @Bean
    public UserRepository userRepository() {
        return new UserRepository();
    }

    @Bean
    public UserService userService(UserRepository userRepository) {
        return new UserService(userRepository);
    }

    @Bean
    public HttpClient httpClient() {
        return new ReactorNettyHttpClient();
    }

    @Bean
    public ServerHttpClient serverHttpClient() {
        return new ServerHttpClientBuilder()
                .httpClient(httpClient())
                .port(8080)
                .build();
    }
}
