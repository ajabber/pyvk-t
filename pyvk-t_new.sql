-- phpMyAdmin SQL Dump
-- version 2.11.9.2
-- http://www.phpmyadmin.net
--

SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";

--
-- Структура таблицы `users`
--

CREATE TABLE IF NOT EXISTS `users` (
  `jid` varchar(30) NOT NULL,
  `email` varchar(30) NOT NULL,
  `pass` varchar(30) NOT NULL,
  UNIQUE KEY `jid` (`jid`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
