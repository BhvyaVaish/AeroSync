import React from 'react';
import './Button.css';

export const Button = ({ 
  children, 
  variant = 'primary', // primary, secondary, ghost
  size = 'md', // sm, md, lg
  className = '',
  icon,
  ...props 
}) => {
  return (
    <button 
      className={`btn btn-${variant} btn-${size} ${className}`}
      {...props}
    >
      {icon && <span className="btn-icon">{icon}</span>}
      {children}
    </button>
  );
};
