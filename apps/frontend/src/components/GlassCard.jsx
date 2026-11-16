import React from 'react';
import './GlassCard.css';

export const GlassCard = ({ children, className = '', hoverEffect = false, ...props }) => {
  return (
    <div 
      className={`glass-card ${hoverEffect ? 'hover-effect' : ''} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
